# Min-Stoughton VIC-3D Post-Processing

## Automatic Metadata Extraction From VIC3D XML

The post-processing pipeline can read fixed specimen and test metadata from
the VIC-3D `project.xml` file or the lab `sample_ID.xml` file. This is used
only for metadata and automatic parameter filling.

`project.xml` is used to extract:

- specimen ID, material code, punch code, width code, test number, and campaign
- sheet thickness inferred from the campaign code in the project/test path,
  for example `2026_04_13_A`
- punch diameter/radius inferred from the punch code, for example `000`
- specimen width inferred from the width code, for example `W20`
- VIC correlation settings such as subset size, step size, criterion,
  interpolation, weights, strain window, and strain filter
- reference/deformed image sequence metadata
- summary camera/AOI metadata

The VTK/OUT exports remain the source of frame-resolved DIC data:

- `X, Y, Z`
- `U, V, W`
- `eps1, eps2`
- valid point masks
- full point-cloud fields over time

## Nakazima D And R_out Coordinates

The Nakazima coordinate `D` is computed as the cumulative 3D distance
along the ordered deformed DIC points of each matrix column. This is the
discrete VIC3D implementation of the arc-distance coordinate described in
the Min-Stoughton paper.

No ideal spherical projection is applied to define `D`, because the
measured DIC geometry is retained. The localized dimple remains represented
through the `R_out` perturbation, where `R_out` is the distance from each
deformed DIC point to the reconstructed punch center `O_prime`.

For normal Nakazima operation, the user should tune only method parameters:

- `W_X`
- `W_Y`
- `SAC`
- `n`
- reference-frame selection through `ReferenceConfig`

The sheet thickness `t0` is inferred from the file path campaign code, not
from the numeric `Thickness` field in `sample_ID.xml`, because that field can
be zero. The punch radius `r_N` is taken from `VICProjectMetadata` and passed
into the Nakazima transform automatically. Unknown project codes are not
guessed silently. Add the code to the mapping tables in
`vic_project_metadata.py` or provide `MetadataOverride`.

Example:

```python
from nakazima_transform import ReferenceConfig
from vic_project_metadata import MethodConfig, run_from_vic_project

result = run_from_vic_project(
    project_xml_path="pics/project.xml",
    dic_data_path="/path/to/specimen",
    crack_data_path="/path/to/specimen/Results/CrackData.txt",
    method_config=MethodConfig(
        W_X=2.0,
        W_Y=20.0,
        SAC=5.0e-4,
        n=8,
        reference_config=ReferenceConfig(
            reference_mode="time_fraction",
            ref_fraction=0.75,
        ),
        pole_mode="max_z",
        pole_search_center=(0.0, 0.0),
        pole_search_radius=15.0,
    ),
)
```
