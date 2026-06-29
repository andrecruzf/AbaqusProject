#!/usr/bin/env python3
"""VIC XML metadata extraction for Min-Stoughton processing.

This module reads fixed specimen/test metadata and VIC correlation settings
from ``project.xml`` or the lab ``sample_ID.xml``. It does not read
frame-resolved DIC fields; geometry, displacements, strains, and valid masks
still come from the VTK/OUT exports through the existing loader.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET


THICKNESS_CLASS_TO_MM = {
    "A": 1.25,
    "B": 1.5,
    "C": 2.0,
    "D": 3.0,
}

PUNCH_CODE_TO_DIAMETER_MM = {
    "000": 100.0,
    "014": 40.0,
    "016": 60.0,
    "018": 80.0,
}

CAMPAIGN_RE = re.compile(r"(?P<campaign>\d{4}_\d{2}_\d{2}_(?P<class>[A-Z]))")
SPECIMEN_RE = re.compile(
    r"(?P<specimen_id>"
    r"(?P<base_specimen_id>"
    r"(?P<experiment>E\d+)_"
    r"(?P<material_code>[A-Z]{2}\d{2})_"
    r"(?P<punch_code>\d{3})"
    r")_"
    r"(?P<width_code>W(?P<width_digits>\d+))_"
    r"(?P<test_number>\d+)"
    r")"
)
IMAGE_NUMBER_RE = re.compile(r"-(?P<number>\d+)_\d+\.(?:tiff?|out)$", re.I)


@dataclass(frozen=True)
class MetadataOverride:
    """Explicit physical metadata overrides for unknown project codes."""

    sheet_thickness_mm: Optional[float] = None
    punch_diameter_mm: Optional[float] = None
    punch_radius_mm: Optional[float] = None
    specimen_width_mm: Optional[float] = None


@dataclass(frozen=True)
class SpecimenMetadata:
    """Fixed specimen/test metadata inferred from the VIC project."""

    specimen_id: Optional[str]
    campaign: Optional[str]
    material_code: Optional[str]
    thickness_class: Optional[str]
    sheet_thickness_mm: float
    sheet_thickness_source: str
    punch_code: Optional[str]
    punch_diameter_mm: float
    punch_radius_mm: float
    punch_source: str
    width_code: Optional[str]
    specimen_width_mm: float
    specimen_width_source: str
    test_number: Optional[str]


@dataclass(frozen=True)
class VICProjectMetadata(SpecimenMetadata):
    """Metadata extracted from a VIC/lab XML metadata file."""

    # Project and specimen identity
    project_xml_path: Path
    original_project_path: Optional[str]
    base_specimen_id: Optional[str]
    test_type: str = "nakazima"

    # Image and frame sequence
    reference_image: Optional[str] = None
    reference_image_number: Optional[int] = None
    deformed_images: tuple[str, ...] = ()
    first_deformed_image: Optional[str] = None
    last_deformed_image: Optional[str] = None
    first_deformed_image_number: Optional[int] = None
    last_deformed_image_number: Optional[int] = None
    n_deformed_images: int = 0
    out_files: tuple[str, ...] = ()
    n_out_files: int = 0
    crack_frame: Optional[int] = None
    crack_frame_source: str = "not_available_in_project_xml"

    # VIC correlation settings
    subset_size: Optional[int] = None
    step_size: Optional[int] = None
    criterion: Optional[str] = None
    interpolation: Optional[str] = None
    weights: Optional[str] = None
    incremental_correlation: Optional[bool] = None
    strain_computation: Optional[bool] = None
    principal_strains: Optional[bool] = None
    strain_window: Optional[int] = None
    strain_filter: Optional[int] = None

    # Camera/calibration summary
    n_cameras: int = 0
    camera_model: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    calibration_available: bool = False
    mask_available: bool = False
    mask_image_width: Optional[int] = None
    mask_image_height: Optional[int] = None

    def to_output_dict(self) -> dict[str, Any]:
        """Compact metadata dict for final result/report output."""
        return {
            "specimen_id": self.specimen_id,
            "campaign": self.campaign,
            "material_code": self.material_code,
            "thickness_class": self.thickness_class,
            "sheet_thickness_mm": self.sheet_thickness_mm,
            "sheet_thickness_source": self.sheet_thickness_source,
            "punch_code": self.punch_code,
            "punch_diameter_mm": self.punch_diameter_mm,
            "punch_radius_mm": self.punch_radius_mm,
            "punch_source": self.punch_source,
            "width_code": self.width_code,
            "specimen_width_mm": self.specimen_width_mm,
            "specimen_width_source": self.specimen_width_source,
            "test_number": self.test_number,
            "reference_image": self.reference_image,
            "first_deformed_image": self.first_deformed_image,
            "last_deformed_image": self.last_deformed_image,
            "n_deformed_images": self.n_deformed_images,
            "subset_size": self.subset_size,
            "step_size": self.step_size,
            "criterion": self.criterion,
            "interpolation": self.interpolation,
            "weights": self.weights,
            "strain_window": self.strain_window,
            "strain_filter": self.strain_filter,
        }


@dataclass(frozen=True)
class MethodConfig:
    """User-tuned Min-Stoughton method parameters."""

    W_X: float
    W_Y: float
    SAC: float
    n: int
    reference_config: Any
    delta: Optional[float] = None
    pole_mode: str = "max_z"
    pole_xy: Optional[tuple[float, float]] = None
    pole_search_center: Optional[tuple[float, float]] = None
    pole_search_radius: Optional[float] = None
    z_convention: str = "z_down"
    n_columns: Optional[int] = None
    min_points_per_column: int = 8


@dataclass
class MinStoughtonProjectResult:
    """High-level result returned by ``run_from_vic_project``."""

    metadata: VICProjectMetadata
    method_config: MethodConfig
    dic: Any
    region: Any
    curvature_matrix: Any
    signal: Any
    nakazima: Any
    reference_metadata: Any
    onset: Any
    limit_strains: Any
    output_metadata: dict[str, Any]


def _option_map(root: ET.Element) -> dict[str, str]:
    opts: dict[str, str] = {}
    for opt in root.findall(".//option"):
        name = opt.attrib.get("name")
        if not name:
            continue
        opts[name] = opt.attrib.get("value", (opt.text or "").strip())
    return opts


def _as_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(float(value))


def _as_bool(value: Optional[str]) -> Optional[bool]:
    if value is None or value == "":
        return None
    return value.strip().lower() in {"1", "true", "yes"}


def _image_number(name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    match = IMAGE_NUMBER_RE.search(name.strip())
    return int(match.group("number")) if match else None


def _text_list(root: ET.Element, tag: str, suffix: Optional[str] = None) -> tuple[str, ...]:
    values = []
    for elem in root.findall(f".//{tag}"):
        text = (elem.text or "").strip()
        if not text:
            continue
        if suffix is not None and not text.lower().endswith(suffix.lower()):
            continue
        values.append(text)
    return tuple(values)


def _sample_id_params(root: ET.Element) -> dict[str, str]:
    params: dict[str, str] = {}
    for elem in root.findall(".//Parameter"):
        name = elem.attrib.get("name")
        if name:
            params[name] = elem.attrib.get("value", "")
    return params


def _original_project_path(root: ET.Element) -> Optional[str]:
    if root.tag == "project":
        return root.attrib.get("dir") or None
    if root.tag == "Sample_ID":
        params = _sample_id_params(root)
        return params.get("Test Path") or None
    return root.attrib.get("dir") or None


def _width_mm_from_code(width_code: Optional[str], override: Optional[float]) -> tuple[float, str]:
    if override is not None:
        return float(override), "user_override"
    if width_code is None:
        raise ValueError(
            "Missing width code. Provide MetadataOverride(specimen_width_mm=...)."
        )
    match = re.fullmatch(r"W(?P<digits>\d+)", width_code)
    if match is None:
        raise ValueError(
            f"Unknown width code {width_code!r}. Provide "
            "MetadataOverride(specimen_width_mm=...)."
        )
    digits = match.group("digits")
    value = int(digits)
    if len(digits) == 2:
        return float(value * 10), "inferred_from_width_code"
    if len(digits) == 3:
        return float(value), "inferred_from_width_code"
    raise ValueError(
        f"Unknown width code {width_code!r}. Provide "
        "MetadataOverride(specimen_width_mm=...)."
    )


def _sheet_thickness(
    thickness_class: Optional[str],
    override: Optional[float],
) -> tuple[float, str]:
    if override is not None:
        return float(override), "user_override"
    if thickness_class is None:
        raise ValueError(
            "Missing thickness class. Provide "
            "MetadataOverride(sheet_thickness_mm=...)."
        )
    if thickness_class not in THICKNESS_CLASS_TO_MM:
        raise ValueError(
            f"Unknown thickness class {thickness_class!r}. Provide "
            "MetadataOverride(sheet_thickness_mm=...)."
        )
    return THICKNESS_CLASS_TO_MM[thickness_class], "inferred_from_campaign_code"


def _punch_geometry(
    punch_code: Optional[str],
    override: MetadataOverride,
    tolerance: float = 1e-9,
) -> tuple[float, float, str]:
    od = override.punch_diameter_mm
    orad = override.punch_radius_mm
    if od is not None and orad is not None:
        if abs(float(orad) - float(od) / 2.0) >= tolerance:
            raise ValueError(
                "Inconsistent punch override: punch_radius_mm must equal "
                "punch_diameter_mm / 2."
            )
        return float(od), float(orad), "user_override"
    if od is not None:
        diameter = float(od)
        return diameter, diameter / 2.0, "user_override"
    if orad is not None:
        radius = float(orad)
        return radius * 2.0, radius, "user_override"
    if punch_code is None:
        raise ValueError(
            "Missing punch code. Provide MetadataOverride(punch_diameter_mm=...) "
            "or MetadataOverride(punch_radius_mm=...)."
        )
    if punch_code not in PUNCH_CODE_TO_DIAMETER_MM:
        raise ValueError(
            f"Unknown punch code {punch_code!r}. Provide "
            "MetadataOverride(punch_diameter_mm=...) or update "
            "PUNCH_CODE_TO_DIAMETER_MM."
        )
    diameter = PUNCH_CODE_TO_DIAMETER_MM[punch_code]
    return diameter, diameter / 2.0, "inferred_from_punch_code"


def _identity_from_project_path(project_path: Optional[str]) -> dict[str, Optional[str]]:
    text = project_path or ""
    campaign_match = CAMPAIGN_RE.search(text)
    specimen_match = SPECIMEN_RE.search(text)

    out: dict[str, Optional[str]] = {
        "campaign": None,
        "thickness_class": None,
        "specimen_id": None,
        "base_specimen_id": None,
        "material_code": None,
        "punch_code": None,
        "width_code": None,
        "test_number": None,
    }
    if campaign_match:
        out["campaign"] = campaign_match.group("campaign")
        out["thickness_class"] = campaign_match.group("class")
    if specimen_match:
        out["specimen_id"] = specimen_match.group("specimen_id")
        out["base_specimen_id"] = specimen_match.group("base_specimen_id")
        out["material_code"] = specimen_match.group("material_code")
        out["punch_code"] = specimen_match.group("punch_code")
        out["width_code"] = specimen_match.group("width_code")
        out["test_number"] = specimen_match.group("test_number")
    return out


def _sequence_metadata(root: ET.Element) -> tuple[Optional[str], tuple[str, ...], tuple[str, ...]]:
    if root.tag != "project":
        return None, (), ()
    references = _text_list(root, "reference", ".tiff")
    deformed = _text_list(root, "deformed", ".tiff")
    out_files = _text_list(root, "datafile", ".out")
    return (references[0] if references else None), deformed, out_files


def parse_project_xml(
    project_xml_path: str | Path,
    overrides: Optional[MetadataOverride] = None,
) -> VICProjectMetadata:
    """Parse VIC/lab XML metadata and infer fixed test parameters.

    Sheet thickness is inferred from the campaign component of the project
    path, for example ``2026_04_13_C``. Numeric thickness fields inside
    ``sample_ID.xml`` are intentionally ignored because they can be zero.
    """
    overrides = overrides or MetadataOverride()
    path = Path(project_xml_path)
    if not path.is_file():
        raise FileNotFoundError(f"VIC metadata XML not found: {path}")

    root = ET.parse(path).getroot()
    original_project_path = _original_project_path(root)
    identity = _identity_from_project_path(original_project_path)

    thickness, thickness_source = _sheet_thickness(
        identity["thickness_class"],
        overrides.sheet_thickness_mm,
    )
    punch_diameter, punch_radius, punch_source = _punch_geometry(
        identity["punch_code"],
        overrides,
    )
    specimen_width, width_source = _width_mm_from_code(
        identity["width_code"],
        overrides.specimen_width_mm,
    )

    reference_image, deformed, out_files = _sequence_metadata(root)
    first_deformed = deformed[0] if deformed else None
    last_deformed = deformed[-1] if deformed else None

    opts = _option_map(root)
    cameras = root.findall(".//camera")
    models = sorted({cam.attrib.get("type", "") for cam in cameras if cam.attrib.get("type")})
    camera_model = models[0] if len(models) == 1 else ", ".join(models) if models else None

    polygon_mask = root.find(".//polygonmask")
    mask_width = _as_int(polygon_mask.attrib.get("width")) if polygon_mask is not None else None
    mask_height = _as_int(polygon_mask.attrib.get("height")) if polygon_mask is not None else None

    return VICProjectMetadata(
        project_xml_path=path,
        original_project_path=original_project_path,
        campaign=identity["campaign"],
        thickness_class=identity["thickness_class"],
        specimen_id=identity["specimen_id"],
        base_specimen_id=identity["base_specimen_id"],
        material_code=identity["material_code"],
        punch_code=identity["punch_code"],
        width_code=identity["width_code"],
        test_number=identity["test_number"],
        sheet_thickness_mm=thickness,
        sheet_thickness_source=thickness_source,
        punch_diameter_mm=punch_diameter,
        punch_radius_mm=punch_radius,
        punch_source=punch_source,
        specimen_width_mm=specimen_width,
        specimen_width_source=width_source,
        reference_image=reference_image,
        reference_image_number=_image_number(reference_image),
        deformed_images=deformed,
        first_deformed_image=first_deformed,
        last_deformed_image=last_deformed,
        first_deformed_image_number=_image_number(first_deformed),
        last_deformed_image_number=_image_number(last_deformed),
        n_deformed_images=len(deformed),
        out_files=out_files,
        n_out_files=len(out_files),
        subset_size=_as_int(opts.get("subset_size")),
        step_size=_as_int(opts.get("step_size")),
        criterion=opts.get("criterion") or None,
        interpolation=opts.get("interpolation") or None,
        weights=opts.get("weights") or None,
        incremental_correlation=_as_bool(opts.get("incremental")),
        strain_computation=_as_bool(opts.get("computestrain")),
        principal_strains=_as_bool(opts.get("computeprincipals")),
        strain_window=_as_int(opts.get("strainwindow")),
        strain_filter=_as_int(opts.get("strainfilter")),
        n_cameras=len(cameras),
        camera_model=camera_model,
        image_width=mask_width,
        image_height=mask_height,
        calibration_available=root.find(".//calibration") is not None and bool(cameras),
        mask_available=polygon_mask is not None,
        mask_image_width=mask_width,
        mask_image_height=mask_height,
    )


def run_from_vic_project(
    project_xml_path: str | Path,
    dic_data_path: str | Path,
    crack_data_path: Optional[str | Path],
    method_config: MethodConfig,
    metadata_overrides: Optional[MetadataOverride] = None,
) -> MinStoughtonProjectResult:
    """Run the Nakazima Min-Stoughton pipeline using project.xml metadata.

    ``project.xml`` supplies fixed metadata and test geometry. DIC geometry
    and field histories are still loaded from ``dic_data_path`` using the
    existing VTK/OUT loader.
    """
    from dic_loader import load_specimen
    from region_selector import RegionConfig, select_region
    from curvature_matrix import build_curvature_matrix
    from nakazima_transform import NakazimaConfig, run_nakazima_pipeline
    from onset_detection import OnsetConfig, detect_onset
    from limit_strains import extract_limit_strains

    metadata = parse_project_xml(project_xml_path, metadata_overrides)
    if crack_data_path is not None and not Path(crack_data_path).is_file():
        raise FileNotFoundError(f"crack data path not found: {crack_data_path}")

    dic = load_specimen(dic_data_path, test_type=metadata.test_type)
    region = select_region(
        dic,
        cfg=RegionConfig(W_X=method_config.W_X, W_Y=method_config.W_Y),
    )
    mat = build_curvature_matrix(dic, region)

    naka_cfg = NakazimaConfig(
        punch_radius=metadata.punch_radius_mm,
        thickness=metadata.sheet_thickness_mm,
        pole_mode=method_config.pole_mode,
        pole_xy=method_config.pole_xy,
        pole_search_center=method_config.pole_search_center,
        pole_search_radius=method_config.pole_search_radius,
        z_convention=method_config.z_convention,
    )
    signal, naka, ref_meta = run_nakazima_pipeline(
        mat,
        dic=dic,
        naka_cfg=naka_cfg,
        ref_cfg=method_config.reference_config,
        k_SAC=method_config.SAC,
        n_columns=method_config.n_columns,
        min_points_per_column=method_config.min_points_per_column,
    )
    onset = detect_onset(
        signal,
        OnsetConfig(
            n_consecutive=method_config.n,
            delta=method_config.delta,
        ),
    )
    limit_strains = extract_limit_strains(onset, mat)

    output_metadata = metadata.to_output_dict()
    output_metadata.update({
        "D_mode": naka.D_mode,
        "D_definition": naka.D_definition,
        "D_units": naka.D_units,
        "R_out_definition": naka.R_out_definition,
    })
    setattr(signal, "project_metadata", metadata)
    setattr(naka, "project_metadata", metadata)
    setattr(naka, "output_metadata", output_metadata)

    return MinStoughtonProjectResult(
        metadata=metadata,
        method_config=method_config,
        dic=dic,
        region=region,
        curvature_matrix=mat,
        signal=signal,
        nakazima=naka,
        reference_metadata=ref_meta,
        onset=onset,
        limit_strains=limit_strains,
        output_metadata=output_metadata,
    )
