

c      SUBROUTINE VUMAT(
cC READ only -
c     1 NBLOCK, NDIR, NSHR, NSTATEV, NFIELDV, NPROPS, LANNEAL,
c     2 STEPTIME, TOTALTIME, DT, CMNAME, COORDMP, CHARLENGTH,
c     3 PROPS, DENSITY, STRAININC, RELSPININC,
c     4 TEMPOLD, STRETCHOLD, DEFGRADOLD, FIELDOLD,
c     5 STRESSOLD, STATEOLD, ENERINTERNOLD, ENERINELASOLD,
c     6 TEMPNEW, STRETCHNEW, DEFGRADNEW, FIELDNEW,
cC WRITE only -
c     7 STRESSNEW, STATENEW, ENERINTERNNEW, ENERINELASNEW)
cC
c      INCLUDE 'VABA_PARAM.INC'
cC
c      DIMENSION PROPS(NPROPS), DENSITY(NBLOCK), COORDMP(NBLOCK),
c     1 CHARLENGTH(NBLOCK), STRAININC(NBLOCK, NDIR+NSHR),
c     2 RELSPININC(NBLOCK, NSHR), TEMPOLD(NBLOCK),
c     3 STRETCHOLD(NBLOCK, NDIR+NSHR),DEFGRADOLD(NBLOCK,NDIR+NSHR+NSHR),
c     4 FIELDOLD(NBLOCK, NFIELDV), STRESSOLD(NBLOCK, NDIR+NSHR),
c     5 STATEOLD(NBLOCK, NSTATEV), ENERINTERNOLD(NBLOCK),
c     6 ENERINELASOLD(NBLOCK), TEMPNEW(NBLOCK),
c     7 STRETCHNEW(NBLOCK, NDIR+NSHR),DEFGRADNEW(NBLOCK,NDIR+NSHR+NSHR),
c     8 FIELDNEW(NBLOCK, NFIELDV), STRESSNEW(NBLOCK,NDIR+NSHR),
c     9 STATENEW(NBLOCK, NSTATEV), ENERINTERNNEW(NBLOCK),
c     1 ENERINELASNEW(NBLOCK)
C

      subroutine vumat (
c    c Read only -
     1 jblock, ndir, nshr, nstatev, nfieldv, nprops, lanneal,
     2 stepTime, totalTime, dt, cmname, coordMp, charLength,
     3 props, density, strainInc, relSpinInc,
     4 tempOld, stretchOld, defgradOld, fieldOld,
     5 stressOld, stateOld, enerInternOld, enerInelasOld,
     6 tempNew, stretchNew, defgradNew, fieldNew,
c    c Write only -
     7 stressNew, stateNew, enerInternNew, enerInelasNew )
c     c
      include 'vaba_param.inc'
c     c
      dimension jblock(*), props(nprops),density(*), coordMp(*),
     1 charLength(*), strainInc(*),
     2 relSpinInc(*), tempOld(*),
     3 stretchOld(*),
     4 defgradOld(*),
     5 fieldOld(*), stressOld(*),
     6 stateOld(*), enerInternOld(*),
     7 enerInelasOld(*), tempNew(*),
     8 stretchNew(*),
     9 defgradNew(*), 
     1 fieldNew(*),
     2 stressNew(*), stateNew(*),
     3 enerInternNew(*), enerInelasNew(*)
c     c
      character*80 cmname
     
      parameter (
     1 i_umt_nblock = 1,
     2 i_umt_npt = 2,
     3 i_umt_layer = 3,
     4 i_umt_kspt = 4,
     5 i_umt_noel = 5 )
     
       call vumatXtrArg ( jblock(i_umt_nblock),
     1 ndir, nshr, nstatev, nfieldv, nprops, lanneal,
     2 stepTime, totalTime, dt, cmname, coordMp, charLength,
     3 props, density, strainInc, relSpinInc,
     4 tempOld, stretchOld, defgradOld, fieldOld,
     5 stressOld, stateOld, enerInternOld, enerInelasOld,
     6 tempNew, stretchNew, defgradNew, fieldNew,
     7 stressNew, stateNew, enerInternNew, enerInelasNew,
     8 jblock(i_umt_noel), jblock(i_umt_npt),
     9 jblock(i_umt_layer), jblock(i_umt_kspt))
     
      return
      end
     
c     ----------------------------------------------------------------------------------
     
      subroutine vumatXtrArg (
c    c read only -
     1 nblock, ndir, nshr, nstatev, nfieldv, nprops, lanneal,
     2 stepTime, totalTime, timeinc, cmname, coordMp, charLength,
     3 props, density, strainInc, relSpinInc,
     4 tempOld, stretchOld, defgradOld, fieldOld,
     3 stressOld, stateOld, enerInternOld, enerInelasOld,
     6 tempNew, stretchNew, defgradNew, fieldNew,
c    c write only -
     5 stressNew, stateNew, enerInternNew, enerInelasNew,
c    c read only extra arguments -
     6 nElement, nMatPoint, nLayer, nSecPoint)
c
       include 'vaba_param.inc'
     
c      all arrays dimensioned by (*) are not used in this algorithm
       dimension props(nprops), density(nblock),
     1 strainInc(nblock,ndir+nshr),
     2 relSpinInc(nblock,nshr), defgradOld(nblock,9),
     4 stressOld(nblock,ndir+nshr),
     5 stateOld(nblock,nstatev), enerInternOld(nblock),
     6 enerInelasOld(nblock),
     7 stretchNew(nblock,ndir+nshr), defgradNew(nblock,9),
     8 stressNew(nblock,ndir+nshr)
     
       dimension enerInelasNew(nblock),stateNew(nblock,nstatev),
     1 enerInternNew(nblock),eigVal(nblock,3)
     
       dimension nElement(nblock),nMatPoint(nblock),nLayer(nblock),
     1 nSecPoint(nblock)
     
      character*80 cmname
c      CHARACTER*8 CMNAME
C
c*****INPUT FORM*****************************************************************
!*USER MATERIAL,CONSTANTS=37
!**Physical constants
!**       E         v        Cp        Xi         -         -         - Fflag(0/1) (FE/BE)
!         1         2         3         4         5         6         7         8
!**Yield function and flow rule>HILL-NAFR
!**     P12       P22       P33       G12       G22       G33         M         -
!         9        10        11        12        13        14        15        16
!**Hardening>MIXED-SWIFT-VOCE
!**       A         B         n        gs                                      (1) HARD JCX
!**      s0        Q1        C1        Q2        C2                            (2) HARD VOCE
!**       A        e0         n        s0        Q1        C1        alpha        (3) HARD MSV
!        17        18        19        20        21        22        23        24
!**SRH+TS>JC
!   eps0dot         C         m        T0        Tr        Tm   epsAdot         -
!        25        26        27        28        29        30        31        32
!**Failure criterion>HC
!**ADDFail (+) Tc, (-) EQPSmax
!**     Wcr                                                               ADDFail  (0/1) FAILURE CL
!**       a         b         c         n        D4        D5             ADDFail  (2/3) FAILURE HC
!**      D1        D2        D3        gf        D4        D5             ADDFail  (4/5) FAILURE JCX
!        33        34        35        36        37        38        39        40
!**Post initiation damage
!**      D0        Dc        mD     DcMax    bMinS          k
!        41        42        43        44       45         46
!*DEPVAR, DELETE=7
!16
!1,EQPS,"Equivalent Plastic Strain"
!2,Seq,"Equivalent stress"
!3,Qeq,"Equivalent Hill stress"
!4,TRIAX,"Triaxiality"
!5,LODE,"Lode parameter"
!6,D,"Damage"
!7,FAIL,"Failure switch"
!8,Beta,"Softening function"
!9,eeV,"Volumetric strain"
!10,T,"Temperature"
!11,EQPSdot,"Equivalent Plastic Strain rate"
!12,ySRH,"Strain rate hardening"
!13,yTS,"Thermal softening"
!14,fSR,"Failure strain rate"
!15,fTS,"Failure thermal softening"
!16,Wcl,"CL plastic work"
!17,EQPSf,"EQPSf"

      PARAMETER( zero = 0.d0, one = 1.d0, two = 2.d0, THREE = 3.d0,
     1           third = 1.d0 / 3.d0, half = 0.5d0, op5 = 1.5d0)
C
      INTEGER i, j, k, K1, K2, HARDflag, FAILflag, ITER, NEWTON
      REAL*8 PP(6,6), GG(6,6), CC(6,6)
      REAL*8 S(6), St(6), Sd(6), dd(6), N(6), M(6), a_par(4)
      REAL*8 PPxS(6), GGxS(6), CCxM(6), CCxN(6)
      REAL*8 KK, E, NU, G1, G2, G3, BULK, LAMBDA
      REAL*8 P12, P22, P33, G12, G22, G33
      REAL*8 NxCxM, dlambda, ddlambda
      REAL*8 Sh, Seq, Qeq, TRIAX, LODE
      REAL*8 eqpsOld, yOld, deqps, Aeev, eqpsNew, yNew
      REAL*8 YFACTOR, PHI, omega
      REAL*8 eevOld, eevNew, Aeqs, eqsDot
      REAL*8 AWp, AT, Xi, Cp, T0, Tr, Tm
      REAL*8 Dold, Dnew, FAILURE
      REAL*8 bOld, bNEw, Hbeta, DcMax, bMinS
      REAL*8 ySRH, yTS, fSR, fTS, Lk
      REAL*8 ySRH0, yTS0, fSR0, fTS0
C
C**********************************************************************
C     CONSTANTS
C**********************************************************************
      E      = PROPS(1)
      NU     = PROPS(2)
      Cp     = PROPS(3)
      Xi     = PROPS(4)
      BULK   = E/(THREE*(ONE-TWO*NU))
      LAMBDA = BULK-G2/THREE
      P12    = PROPS(9)
      P22    = PROPS(10)
      P33    = PROPS(11)
      G12    = PROPS(12)
      G22    = PROPS(13)
      G33    = PROPS(14)
      Eps0   = PROPS(25)
      C      = PROPS(26)
      T0     = PROPS(28)
      EpsA   = PROPS(31)
      IF (FAILflag.le.1)THEN
      WCR    = PROPS(33)
      END IF
      Dcmax  = PROPS(44)
      bMinS  = PROPS(45)
      G2     = E/(ONE+NU)
      G3     = OP5*G2
      G1     = G2/TWO
      TOLER  = 1d-3
      NEWTON = 150

c     HARDENING TYPE: (1) JCX; (2) VOCE; (3) MSV
      HARDflag = PROPS(24)
c     ADDITIONAL FAILURE
c     (0) NO FAILURE; (+) Critical Temperature; (-) MAX EQPS
      ADDFAIL  = PROPS(39)
c     FAILURE TYPE: (0/1) NO/YES CL; (0/1) NO/YES HC; (0/1) NO/YES JCX
      FAILflag = PROPS(40)

C**********************************************************************
C     COMPUTE THE MATRICES
C**********************************************************************
C     COMPUTE HILL TENSOR
      DO i = 1, NDIR+NSHR
        DO j = 1, NDIR+NSHR
          PP(i,j) = ZERO
        END DO
      END DO
      PP(1,1) = ONE
      PP(1,2) = P12
      PP(1,3) = -(ONE+P12)
      PP(2,1) = PP(1,2)
      PP(2,2) = P22
      PP(2,3) = -(P22+P12)
      PP(3,1) = PP(1,3)
      PP(3,2) = PP(2,3)
      PP(3,3) = ONE+TWO*P12+P22
      PP(4,4) = P33
      PP(5,5) = THREE
      PP(6,6) = THREE
C     COMPUTE NAFR TENSOR
      DO i = 1, NDIR+NSHR
        DO j = 1, NDIR+NSHR
          GG(i,j) = ZERO
        END DO
      END DO
      GG(1,1) = ONE
      GG(1,2) = G12
      GG(1,3) = -(ONE+G12)
      GG(2,1) = GG(1,2)
      GG(2,2) = G22
      GG(2,3) = -(G22+G12)
      GG(3,1) = GG(1,3)
      GG(3,2) = GG(2,3)
      GG(3,3) = ONE+TWO*G12+G22
      GG(4,4) = G33
      GG(5,5) = THREE
      GG(6,6) = THREE


C**********************************************************************
C     Variable initialisation
C**********************************************************************

      IF ( stepTime .eq. zero ) THEN
        do k = 1, nblock
          call STRAIN_RATE_HARD(ySRH0,HSRH,Eps0,PROPS)
          call THERMAL_SOFT(yTS0,HSRH,T0,PROPS)
          call STRAIN_RATE_FAIL(fSR0,Eps0,PROPS)
          call THERMAL_SOFT_FAIL(fTS0,T0,PROPS)
          stateOld(k,8)   = ONE
          bOld            = stateOld(k,8)  !Softening
          stateOld(k,10)  = T0             !INITIAL temperature
          stateOld(k,11)  = Eps0           !INITIAL strain rate
          stateOld(k,12)  = ySRH0          !INITIAL strain rate hardening
          stateOld(k,13)  = yTS0           !INITIAL thermal softening
          stateOld(k,14)  = fSR0           !INITIAL failure strain rate term
          stateOld(k,15)  = fTS0           !INITIAL failure thermal softening
          Aepsv = strainInc(k,1)+strainInc(k,2)+strainInc(k,3)
           DO i= 1, NDIR
           stressNew(k,i) = stressOld(k,i)+G2*strainInc(k,i)+BULK*Aepsv
           END DO
           DO i = NDIR+1, NDIR+NSHR
           stressNew(k,i) = stressOld(k,i)+G2*strainInc(k,i)
           END DO
        end do

      ELSE

        do k = 1, nblock
C**********************************************************************
C         STATE VARIABLES OLD
C**********************************************************************
          NUMEL   = nElement(k)
          eqpsOld = stateOld(k,1)     !EQPS*n+1
          Dold    = stateOld(k,6)     !Dn
          FAILURE = stateOld(k,7)     !FAILURE SWITCH
          bOld    = stateOld(k,8)     !Softening
          eevOld  = stateOld(k,9)     !Volumetric strain
          Told    = stateOld(k,10)    !Temperature
          eqpsDot = stateOld(k,11)    !EQPSrate
          fSR     = stateOld(k,14)    !failure strain rate term
          fTS     = stateOld(k,15)    !failure thermal softening
          WclOld  = stateOld(k,16)    !CL plastic energy
          EQPSf   = stateNew(k,17)    !EQPSf
C**********************************************************************
C         STRAIN INCREMENT
C**********************************************************************
c         COMPUTE VOLUMETRIC STRAINe INCREMENT (Aepsv)
          Aepsv = strainInc(k,1)+strainInc(k,2)+strainInc(k,3)
          eevNew = eevOld + Aepsv
C**********************************************************************
C         ELASTIC STIFFNESS MATRIX
C**********************************************************************
          bStar  = dmax1(bMinS, bOld)
          E      = bStar*PROPS(1)
          G2     = E/(ONE+NU)
          G3     = OP5*G2
          G1     = G2/TWO
          IF (eevNew.le.ZERO) THEN
c           Hydrostatic compression
            BULK = PROPS(1)/(THREE*(ONE-TWO*NU))
            ELSE
c           Hydrostatic tension (fluid-like behaviour)
            BULK   = E/(THREE*(ONE-TWO*NU))
          ENDIF
          LAMBDA = BULK-G2/THREE
          DO i = 1, NDIR+NSHR
            DO j = 1, NDIR+NSHR
              CC(i,j) = ZERO
            END DO
          END DO
          DO K1 = 1, NDIR
            DO K2 = 1, NDIR
              CC(K2, K1) = LAMBDA
            END DO
            CC(K1, K1) = G2 + LAMBDA
          END DO
          DO K1 = NDIR+1, NDIR+NSHR
            CC(K1, K1) = G1
          END DO

C**********************************************************************
C         ELASTIC PREDICTOR
C**********************************************************************

c         TRIAL deviatoric Strain tensor Incremental
            DO i = 1, NDIR
            dd(i) = strainInc(k,i)-THIRD*Aepsv
            END DO
            DO i = NDIR+1, NDIR+NSHR
            dd(i) = strainInc(k,i)
            END DO

c         COMPUTE TRIAL STRESS TENSOR (S*n+1=Sn+2G*Aee+K*Aepsv)
            DO i = 1, NDIR
            st(i) = stressOld(k,i)+G2*dd(i)+BULK*Aepsv
            END DO
            DO i = NDIR+1, NDIR+NSHR
            st(i) = stressOld(k,i)+G2*dd(i)
            END DO

c         COMPUTE TRIAL HYDROSTATIC STRESS (Sh*n+1=Shn+1=Sh=1/3tr(s))
          sh = THIRD*(st(1)+st(2)+st(3))
c         COMPUTE TRIAL DEVIATORIC STRESS TENSOR (Sd*n+1=S*n+1-Sh*I)
            DO i = 1, NDIR
            sd(i) = st(i) - sh
            END DO
            DO i = NDIR+1, NDIR+NSHR
            sd(i) = st(i)
            END DO
c         COMPUTE Qeq*n+1 = SQRT(sT*G*s)
          CALL PMxV(PPxS,PP,st)
          CALL PVxV(Seq,st,PPxS)
          Seq = DSQRT(Seq)
c         COMPUTE Qeq*n+1 = SQRT(sT*G*s)
          CALL PMxV(GGxS,GG,st)
          CALL PVxV(Qeq,st,GGxS)
          Qeq = DSQRT(Qeq)

c         COMPUTE TRIAX AND INVARIANTS (Seq*n+1,T*n+1,L*n+1)
          CALL INVARIANTS(TRIAX,Svm,LODE,sd,SH)

c**********************************************************************
c         HARDENING JCX                                               *
c**********************************************************************
        IF (HARDflag.eq.1) THEN
c       Compute trial strain hardening Y*n+1 = function(EQPS*n+1)
        call JCX_HARD(ySH,HSH,eqpsOld,LODE,PROPS)
        ENDIF
c**********************************************************************
c         HARDENING VOCE                                              *
c**********************************************************************
        IF (HARDflag.eq.2) THEN
c       Compute trial strain hardening Y*n+1 = function(EQPS*n+1)
        call VOCE_HARD(ySH,HSH,eqpsOld,PROPS)
        ENDIF
c**********************************************************************
c         HARDENING MIXED SWIFT-VOCE                                  *
c**********************************************************************
        IF (HARDflag.eq.3) THEN
c       Compute trial strain hardening Y*n+1 = function(EQPS*n+1)
        call SWIFT_VOCE_HARD(ySH,HSH,eqpsOld,PROPS)
        ENDIF
c**********************************************************************

c       Compute strain rate hardening
        call STRAIN_RATE_HARD(ySRH,HSRH,eqpsDot,PROPS)
c       Compute thermal softening
        call THERMAL_SOFT(yTS,HTS,TOld,PROPS)
c       TOTAL hardening
        yOld = ySH*ySRH*yTS

        CALL EIGENVALUES(SIGMA1,SIGMA2,SIGMA3,
     1                   st(1),st(2),st(3),st(4),st(5),st(6))
        PMAXEIGEN = MAX(ZERO,SIGMA1)

c       **********************************************************************
c                FAILURE CL                                                  *
c       **********************************************************************
        IF (FAILflag.le.1) THEN
        fL = ZERO
        ENDIF
c       **********************************************************************
c                FAILURE HC                                                  *
c       **********************************************************************
        IF ((FAILflag.eq.2).or.(FAILflag.eq.3)) THEN
c       Compute trial EQPSf*n+1
        CALL FC_HC(fL,TRIAX,LODE,PROPS)
        ENDIF
c       **********************************************************************
c                FAILURE JCX                                                 *
c       **********************************************************************
         IF ((FAILflag.eq.4).or.(FAILflag.eq.5)) THEN
c        Compute trial EQPSf*n+1
         call FC_JCX(fL,TRIAX,LODE,PROPS)
         ENDIF
c       **********************************************************************
       
c        Compute failure strain rate term
         CALL STRAIN_RATE_FAIL(fSR,eqpsDot,PROPS)
c        Compute failure thermal softening term
         call THERMAL_SOFT_FAIL(fTS,TOld,PROPS)
c        TOTAL trial EQPSf*n+1
         EQPSf = fL*fSR*fTS

c       Compute trial softening b*n+1
        call SOFT(bOld,Hbeta,Dold,PROPS)

C**********************************************************************
C         YIELDING
C**********************************************************************
C         COMPUTE YIELD FUNCTION (phi=Seq*n+1-Y*n+1)
          PHI = seq - bOld*yOld

c         PLASTIC LOADING CONDITION
          IF ( PHI .gt. ZERO ) THEN 

C**********************************************************************
C         PLASTIC CORRECTOR (Backward-EULER/Forward-EULER)
C**********************************************************************
c         Tensor notation
c         Al = phi / ( n:C:m + H*(Qeq/Seq) )
c         Matrix notation
c         Al = phi / ( nT*C*m + H*(Qeq/Seq) )
C         COMPUTE flow vectors n and m VECTOR
           DO i = 1, NDIR+NSHR
           N(i) = PPxS(i)/Seq
           M(i) = GGxS(i)/Qeq
           END DO
c         Compute C:m
          CALL PMxV(CCxM,CC,M)
c         Compute n:C:m
          CALL PVxV(NxCxM,N,CCxM)

c         CUTTING-PLANE ALGORITHM
c         FIRST GUESS--------------------------------------------------
c         dAl_0
          Forflag = PROPS(8)
          dlambdaOld = ZERO
c         ---------------------------------------------------------------
          ITER      = ZERO
          DO KK = 1, NEWTON
            ddlambda = ZERO
            deqps    = ZERO
            AT       = ZERO
c           Plastic multiplier increment dAl for HC&JCX
            IF (FAILflag.gt.1) THEN
   20       ddlambda = PHI/(NxCxM+(Qeq/Seq)*
     1               (HSH*ySRH*yTS*bOld+
     2                HSRH*(ONE/timeinc)*ySH*yTS*bOld+
     3                HTS*(omega*Xi*Seq/(Cp*density(k)))*ySH*ySRH*bOld+
     4                Hbeta*(ONE/EQPSf)*ySH*ySRH*yTS))
            ENDIF
c           Plastic multiplier increment dAl for CL
            IF (FAILflag.le.1) THEN
   21       ddlambda = PHI/(NxCxM+(Qeq/Seq)*
     1               (HSH*ySRH*yTS*bOld+
     2                HSRH*(ONE/timeinc)*ySH*yTS*bOld+
     3                HTS*(omega*Xi*Seq/(Cp*density(k)))*ySH*ySRH*bOld+
     4                Hbeta*(PMAXEIGEN/WCR)*ySH*ySRH*yTS))
             ENDIF
c           Plastic multiplier increment Al
   30       dlambdaNew = dlambdaOld + ddlambda
c           Equivalent plastic strain increment AEQPS
            deqps = dlambdaNew*(Qeq/Seq)
C           ***********************************************************
C           PLASTIC UPDATE
C           ***********************************************************
c           Update EQPSk+1 (EQPSk+1 = EQPSn + Aeqps)
            eqpsNew = eqpsOld + deqps

c           Update EQPSrk+1
            eqpsDot = dmax1(Eps0,deqps/timeinc)

c           UPDATE THE STRESS TENSORS (Sdk+1=Sd*k+1-Al*C:m,Sn+1=Sk+1+Sh*I )
            DO i = 1, NDIR
            s(i)  = st(i) - dlambdaNew*CCxM(i)
            stressNew(k,i) = s(i)
            sd(i) = s(i) - sH
            ENDDO
            DO i = NDIR+1, NDIR+NSHR
            s(i)  = st(i) - dlambdaNew*CCxM(i)
            stressNew(k,i) = s(i)
            sd(i) = s(i)
            ENDDO

C          UPDATE Seqn+1
           CALL PMxV(PPxS,PP,s)
           CALL PVxV(Seq,s,PPxS)
           Seq = DSQRT(Seq)
       
c          COMPUTE Qeqn+1
           CALL PMxV(GGxS,GG,s)
           CALL PVxV(Qeq,s,GGxS)
           Qeq = DSQRT(Qeq)
       
c          Update Temperature Tk+1
           IF (eqpsDot .LT. Eps0) THEN
             omega  = ZERO
             ELSE IF (eqpsDot .GT. EpsA) THEN
             omega  = ONE  
             ELSE 
             denom     = ( Eps0-EpsA )**THREE
             a_par(0)  = ( Eps0**TWO * (-THREE*EpsA+Eps0) ) / denom
             a_par(1)  = ( TWO*THREE*EpsA*Eps0 ) / denom
             a_par(2)  = -( THREE*(Eps0+EpsA) ) / denom
             a_par(3)  =   TWO / denom
             omega = a_par(0)+a_par(1)*eqpsDot+
     1             a_par(2)*(eqpsDot)**TWO+a_par(3)*(eqpsDot)**THREE
            END IF
            AWp  = Seq*deqps
            AT   = omega*Xi*AWp/(Cp*density(k))
            Tnew = Told + AT
       
c           UPDATE TRIAX AND INVARIANTS (Seqk+1,Tk+1,Lk+1)
            CALL INVARIANTS(TRIAX,Svm,LODE,sd,SH)

c           **********************************************************************
c                    HARDENING JCX                                               *
c           ***************************************************************
            IF (HARDflag.eq.1) THEN
c           Compute strain hardening Yk+1 = function(EQPSk+1)
            call JCX_HARD(ySH,HSH,eqpsNew,LODE,PROPS)
            ENDIF
c           **********************************************************************
c                    HARDENING VOCE                                              *
c           **********************************************************************
            IF (HARDflag.eq.2) THEN
c           Compute strain hardening Yk+1 = function(EQPSk+1)
            call VOCE_HARD(ySH,HSH,eqpsNew,PROPS)
            ENDIF
c           **********************************************************************
c                    HARDENING MIXED SWIFT-VOCE                                  *
c           **********************************************************************
            IF (HARDflag.eq.3) THEN
c           Compute strain hardening Yk+1 = function(EQPSk+1)
            call SWIFT_VOCE_HARD(ySH,HSH,eqpsNew,PROPS)
            ENDIF
c           **********************************************************************
         
c           Compute strain rate hardening
            call STRAIN_RATE_HARD(ySRH,HSRH,eqpsDot,PROPS)
c           Compute thermal softening
            call THERMAL_SOFT(yTS,HTS,TNew,PROPS)
c           TOTAL hardening
            yNew = ySH*ySRH*yTS
         
c           **********************************************************************
c                    FAILURE CL                                                  *
c           **********************************************************************
            IF (FAILflag.le.1) THEN
c           EIGENVALUES stress tensor k+1
            CALL EIGENVALUES(SIGMA1,SIGMA2,SIGMA3,
     1                       s(1),s(2),s(3),s(4),s(5),s(6))
            PMAXEIGEN = MAX(ZERO,SIGMA1)
c           Compute trial DAMAGE PARAMETER Dk+1
            call D_CL(Dnew,WclNew,DOld,WclOld,PMAXEIGEN,deqps,PROPS)
            fL = ZERO
            ENDIF
c           **********************************************************************
c                    FAILURE HC                                                  *
c           ***************************************************************
            IF ((FAILflag.eq.2).or.(FAILflag.eq.3)) THEN
c           Compute EQPSfk+1
            CALL FC_HC(fL,TRIAX,LODE,PROPS)
            ENDIF
c           **********************************************************************
c                    FAILURE JCX                                                 *
c           **********************************************************************
             IF ((FAILflag.eq.4).or.(FAILflag.eq.5)) THEN
c            Compute  EQPSfk+1
             call FC_JCX(fL,TRIAX,LODE,PROPS)
             ENDIF
c           **********************************************************************
      
c            Compute failure strain rate term
             CALL STRAIN_RATE_FAIL(fSR,eqpsDot,PROPS)
c            Compute failure thermal softening term
             call THERMAL_SOFT_FAIL(fTS,TNew,PROPS)
c            TOTAL EQPSf
             EQPSf = fL*fSR*fTS

c            **********************************************************************
c                   DAMAGE ACUMULATION HC&JCX                                     *
c            **********************************************************************
             IF (FAILflag.gt.1) THEN
c            UPDATE DAMAGE PARAMETER Dk+1
             CALL D_LINEAR(Dnew,Dold,EQPSf,deqps,PROPS)
             ENDIF
c            **********************************************************************
             
c            Compute softening bk+1
             call SOFT(bNew,Hbeta,Dnew,PROPS)
             
             
c              CONVERGENCE CHECK******************************************
               PHI = Seq - bNew*yNew


c              Backward-Euler
               IF (DABS(PHI).LT.TOLER*bNew*yNew) GOTO 10
c              Forward-Euler
               IF (Forflag.eq.1) GOTO 10

              ITER = ITER + ONE


C             WRITE WARNING MESSAGE TO THE .MSG FILE-------------------------
              IF (ITER.EQ.NEWTON) THEN
              Forflag = 1

       write(*,*)
       write(*,*)
       write(*,*) '***************************************************'
       write(*,*) '*                                                 *'
       write(*,*) '*               W A R N I N G !                   *'
       write(*,*) '*                                                 *'
       write(*,*) '***************************************************'
       write(*,*) '*                                                 *'
       write(*,*) '* PLASTICITY ALGORITHM DID NOT CONVERGE AFTER     *'
       write(*,*) '*',ITER,'ITERATIONS                          *'
       write(*,*) '*-----------Forward-Euler solution----------------*'
       write(*,*) '*                                                 *'
       write(*,*) '***************************************************'
       write(*,*)'ITER',ITER
       write(*,*)'SH',HSH*ySRH*yTS*bOld
       write(*,*)'SRH',HSRH*(ONE/timeinc)*ySH*yTS*bOld
       write(*,*)'TS',HTS*(Xi*Seq/(Cp*density(k)))*ySH*ySRH*bOld
       write(*,*)'dt',timeinc
       write(*,*)'----------------------------------------------------'
       write(*,*)'ddlambda',ddlambda,'dlambdaOld',dlambdaOld,
     1            'dlambdaNew',dlambdaNew,'deqps',deqps
       write(*,*)'eqpsNew',eqpsNew,'eqpsDot',eqpsDot,'TNew',TNew,
     1            'DNew',DNew
       write(*,*)'ySH',ySH,'ySRH',ySRH,'yTS',yTS,'bNew',bNew
       write(*,*)'HSH',HSH,'HSRH',HSRH,'HTS',HTS,'Hbeta',Hbeta
       write(*,*)'PHI',PHI,'yNew',yNew
       write(*,*)'****************************************************'
       STOP
             IF (FAILflag.gt.1) GOTO 20
             IF (FAILflag.le.1) GOTO 21

            ENDIF
c           --------------------------------------------------------------



            IF (PHI.LT.ZERO) THEN
              IF ((ddlambda.GT.dlambdaOld).and.
     1            (dlambdaOld.GT.ZERO)) THEN
                ddlambda = dlambdaOld/TWO
                ELSE
                ddlambda = ddlambda/10.d0
              ENDIF
            GOTO 30
            ENDIF

            dLambdaOld = dLambdaNew
            bOld       = bNew

        END DO

   10  CONTINUE


          IF ((FAILFLAG.eq.0).or.
     1        (FAILFLAG.eq.2).or.
     2        (FAILFLAG.eq.4)) THEN
c           Elements when Damage = or > Dc
            IF (Dnew .GE. DcMax) THEN
              Dnew = DcMax
            END IF
          ENDIF

!=========FAILURE CRITERION ELEMENT REMOVAL============================
          IF ((FAILFLAG.eq.1).or.
     1        (FAILFLAG.eq.3).or.
     2        (FAILFLAG.eq.5)) THEN
c         Delete elements when Damage = or > Dc
          IF (Dnew .GE. DcMax) THEN
            FAILURE = ZERO
            Dnew = DcMax
          END IF
          ENDIF

!=========ADDITIONAL ELEMENT REMOVAL===================================
c         Delete elements when Temperature = or > Tc
          if (ADDFAIL.gt.ZERO)then
            if (Tnew.ge.ADDFAIL)then
            FAILURE = ZERO
            endif
          endif

c         Delete elements when EqPlasticStrain = or > MAXeqps
          if (ADDFAIL.lt.ZERO)then
            if (eqpsNew.gt.abs(ADDFAIL))then
            FAILURE = ZERO
            endif
          endif
!========================================================================

          enerInelasNew(k) = enerInelasOld(k) + AWp/density(k)
C         Update the state variables
          stateNew(k,1)  = eqpsNew        !EQPS
          stateNew(k,2)  = seq            !EQUIVALENT STRESS f
          stateNew(k,3)  = Qeq            !EQUIVALENT STRESS g
          stateNew(k,4)  = TRIAX          !STRESS TRIAXIALITY
          stateNew(k,5)  = LODE           !LODE PARAMETER
          stateNew(k,6)  = Dnew           !DAMAGE PARAMETER
          stateNew(k,7)  = FAILURE        !FAILURE SWITCH
          stateNew(k,8)  = bNew           !SOFTENING
          stateNew(k,9)  = eevNew         !Volumetric strain
          stateNew(k,10) = Tnew           !Temperature
          stateNew(k,11) = eqpsDot        !EQPSrate
          stateNew(k,12) = ySRH           !Strain rate hardening
          stateNew(k,13) = yTS            !Thermal softening
          stateNew(k,14) = fSR            !Failure Strain rate
          stateNew(k,15) = fTS            !Failure thermal softening
          stateNew(k,16) = WclNew         !Cl plastic energy
          stateNew(k,17) = eqpsF          !EQPSf

         IF (stateNew(k,1).GT.2.0) THEN
          CALL XPLB_EXIT
         END IF

         ELSE
C**********************************************************************
C         ELASTIC UPDATE
C**********************************************************************
c        UPDATE THE STRESS TENSOR (Sdn+1=Sd*n+1,Sn+1=Sdn+1+Sh*I)
           DO i = 1, NDIR+NSHR
           stressNew(k,i) = st(i)
           END DO


C        Update the state variables
         stateNew(k,1)  = eqpsOld        !EQPS
         stateNew(k,2)  = seq            !EQUIVALENT STRESS f
         stateNew(k,3)  = Qeq            !EQUIVALENT STRESS g
         stateNew(k,4)  = TRIAX          !STRESS TRIAXIALITY
         stateNew(k,5)  = LODE           !LODE PARAMETER
         stateNew(k,6)  = Dold           !DAMAGE PARAMETER
         stateNew(k,7)  = FAILURE        !FAILURE SWITCH
         stateNew(k,8)  = bOld           !SOFTENING
         stateNew(k,9)  = eevNew
         stateNew(k,10) = TOld           !Temperature
         stateNew(k,11) = eqpsDot        !EQPSrate
         stateNew(k,12) = ySRH           !Strain rate hardening
         stateNew(k,13) = yTS            !Thermal softening
         stateNew(k,14) = fSR            !Strain rate hardening
         stateNew(k,15) = fTS            !Thermal softening
         stateNew(k,16) = WclOld         !CL plastic work
         stateNew(k,17) = eqpsF          !EQPSf


        END IF

c          if (isnan(bOld))then
c          if(NUMEL.eq.48238)then
c          write(*,*)'============================================'
c          write(*,*)'time',totaltime,TRIAX,LODE,EQPSF,Dnew,bNew
c          endif

        end do
      end if
C
      return
      end















CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC
C     AUXILIARY SUBROUTINES                                           C
CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC
      SUBROUTINE INVARIANTS(TRIAX,SEQ,LODE,VECTOR,SH)
c     Calculate invariants of a symmetric matrix
      IMPLICIT DOUBLE PRECISION (A-Z)
      REAL*8 I1,I2,I3,TRACE2
      REAL*8 CHI, TRIAX, SEQ, LODE, SH, PI
      DIMENSION TENSOR(3,3),TENSOR2(3,3),VECTOR(6)
      PARAMETER(zero=0.d0,one=1.d0,two=2.d0,three = 3.d0,tseven= 27.d0)
      PI = dacos(-ONE)

      CALL VECTORtoMATRIX(TENSOR,VECTOR)
      I1=TENSOR(1,1)+TENSOR(2,2)+TENSOR(3,3)
      
      CALL PMAT(TENSOR2,TENSOR,TENSOR,3,3,3)
      
      TRACE2 = TENSOR2(1,1)+TENSOR2(2,2)+TENSOR2(3,3)      
      I2     = 0.5D0*(I1*I1-TRACE2)
      I3     = TENSOR(1,1)*TENSOR(2,2)*TENSOR(3,3)
     1        +TENSOR(1,2)*TENSOR(2,3)*TENSOR(3,1)
     2        +TENSOR(1,3)*TENSOR(2,1)*TENSOR(3,2)
     3        -TENSOR(1,3)*TENSOR(2,2)*TENSOR(3,1)
     4        -TENSOR(2,3)*TENSOR(3,2)*TENSOR(1,1)
     5        -TENSOR(3,3)*TENSOR(1,2)*TENSOR(2,1)
      IF (I2.eq.ZERO) THEN
        SEQ   = ZERO
        TRIAX = ZERO
        CHI   = ZERO
      ELSE
        SEQ   = DSQRT(THREE*(-I2))
        TRIAX = SH/SEQ
        CHI   = (TSEVEN*I3)/(TWO*SEQ**THREE)
        IF (CHI.gt.ONE ) THEN
          CHI = ONE
        END IF
        IF(CHI.lt.-ONE) THEN
          CHI = -ONE
        END IF
      END IF
      LODE   = ONE - (TWO/PI)*DACOS(CHI)
      RETURN
      END

      SUBROUTINE VECTORtoMATRIX(MATRIX,VECTOR)
      IMPLICIT DOUBLE PRECISION (A-Z)
      DIMENSION VECTOR(6), MATRIX(3,3)
      INTEGER i,j
      DO,i=1,i
        DO,j=1,j
        MATRIX(i,j)=0.D0
        END DO
      END DO
      DO i=1,3
        MATRIX(i,i)=VECTOR(i)
      END DO
      MATRIX(1,2)=VECTOR(4)
      MATRIX(1,3)=VECTOR(6)
      MATRIX(2,3)=VECTOR(5)
      MATRIX(2,1)=VECTOR(4)
      MATRIX(3,1)=VECTOR(6)
      MATRIX(3,2)=VECTOR(5)
      RETURN
      END

      SUBROUTINE PMAT(MATOUT,MAT1,MAT2,id,jd,kd)
C     Matrix product
      IMPLICIT DOUBLE PRECISION (A-Z)
      INTEGER i,j,kk,id,jd,kd
      DIMENSION MAT1(id,kd),MAT2(kd,jd),MATOUT(id,jd)
      DO,i=1,id
         DO,j=1,jd
            MATOUT(i,j)=0.D0
            DO,kk=1,kd
               MATOUT(i,j)=MATOUT(i,j)+MAT1(i,kk)*MAT2(kk,j)
            END DO
         END DO
      END DO
      RETURN
      END

      SUBROUTINE PMXV(VECOUT,MAT,VEC)
C     Matrix product
      IMPLICIT DOUBLE PRECISION (A-Z)
      INTEGER i,j
      DIMENSION MAT(6,6),VEC(6),VECOUT(6)
      DO i = 1, 6
        VECOUT(i) = 0.D0
        DO j= 1, 6
        VECOUT(i) = VECOUT(i) + MAT(i,j)*VEC(j)
        END DO
      END DO
      RETURN
      END

      SUBROUTINE PVxV(POUT,VEC1,VEC2)
      IMPLICIT DOUBLE PRECISION (A-Z)
      DIMENSION VEC1(6),VEC2(6)
      REAL*8 POUT
      INTEGER i,j
      POUT = 0.d0
        DO i=1,6
        POUT = POUT + VEC1(i)*VEC2(i)
        END DO
      RETURN 
      END

      SUBROUTINE PCVxV(POUT,VEC1,VEC2)
      IMPLICIT DOUBLE PRECISION (A-Z)
      DIMENSION VEC1(6),VEC2(6)
      REAL*8 POUT
      INTEGER i,j
      POUT = 0.d0
      TWO  = 2.D0
        DO i=1,3
        POUT = POUT + VEC1(i)*VEC2(i)
        END DO
        DO i=4,6
        POUT = POUT + TWO*VEC1(i)*VEC2(i)
        END DO
      RETURN 
      END

      SUBROUTINE SWIFT_VOCE_HARD(YSH,HSH,eqps,PROPS)
      INCLUDE 'VABA_PARAM.INC'
      DIMENSION PROPS(*)
      REAL*8 A, e0, n, Q, b, s0, alpha, HSH, YSH, eqps
      ONE=1.D0
      ! k=alpha*k1(eps,p)+(1-alpha)*k2(eps,p)
      ! k1=A*(eps,p+e0)**n
      ! k2=Q*(1-exp(-b*eps,p))+sig0
      A     = PROPS(17)
      e0    = PROPS(18)
      n     = PROPS(19)
      s0    = PROPS(20)
      Q     = PROPS(21)
      C     = PROPS(22)
      alpha = PROPS(23)
      YSH=alpha*A*(eqps+e0)**n+(ONE-alpha)*(s0+Q*(ONE-EXP(-C*eqps)))
      HSH=alpha*A*n*(eqps+e0)**(n-ONE)+(ONE-alpha)*Q*C*EXP(-C*eqps)
      RETURN
      END 

      SUBROUTINE VOCE_HARD(YSH,HSH,eqps,PROPS)
      IMPLICIT DOUBLE PRECISION (A-Z)
      DIMENSION PROPS(*)
      REAL*8 s0, Q1, C1, Q2, C2, HSH, YSH, eqps
      ONE=1.D0
      ! Y=s0+Q1*(1-exp(-C1*eps))+Q2*(1-exp(-C2*eps))
      s0    = PROPS(17)
      Q1    = PROPS(18)
      C1    = PROPS(19)
      Q2    = PROPS(20)
      C2    = PROPS(21)
      YSH=s0+Q1*(ONE-EXP(-C1*eqps))+Q2*(ONE-EXP(-C2*eqps))
      HSH=Q1*C1*EXP(-C1*eqps)+Q2*C2*EXP(-C2*eqps)
      RETURN
      END 

      SUBROUTINE JCX_HARD(YSH,HSH,eqps,LODE,PROPS)
      INCLUDE 'VABA_PARAM.INC'
      DIMENSION PROPS(*)
      REAL*8 s0, B, n, HSH, YSH, eqps, Lk, MUs
      ZERO=0.D0
      ONE=1.D0
      ! Y=(s0+B*eps^n)*(1-MU)^k
      s0    = PROPS(17)
      B     = PROPS(18)
      n     = PROPS(19)
      gs    = PROPS(20)
      Lk    = PROPS(46)
      CALL LODE_K2(MUs,LODE,gs,Lk)
      IF (eqps.le.ZERO) THEN
        YSH = s0*MUs
        HSH = ZERO
      ELSE
        YSH = (s0+B*eqps**n)*MUs
        HSH = (n*B*eqps**(n-ONE))*MUs
      ENDIF
      RETURN
      END

      SUBROUTINE STRAIN_RATE_HARD(ySRH,HSRH,eqpsDot,PROPS)
      INCLUDE 'VABA_PARAM.INC'
      DIMENSION PROPS(*)
      REAL*8 ySRH, C, eqpsDot, eps0
      ZERO = 0.D0
      ONE  = 1.D0
      ! ySRH  = 1+C*ln(eqpsDot/eps0)
      C     = PROPS(26)
      Eps0  = PROPS(25)
      IF ((eqpsDot .le. Eps0).or.(C.eq.ZERO)) THEN
        ySRH = ONE
        HSRH = ZERO
        ELSE
        ySRH = ONE + C*dlog(eqpsDot/Eps0)
        HSRH = C/eqpsDot
      ENDIF
      RETURN
      END

      SUBROUTINE THERMAL_SOFT(yTS,HTS,Temp,PROPS)
      INCLUDE 'VABA_PARAM.INC'
      DIMENSION PROPS(*)
      REAL*8 yTS, Temp, T0, Tr, Tm, m, Tstar
      ZERO = 0.D0
      ONE  = 1.D0
      m      = PROPS(27)
      T0     = PROPS(28)
      Tr     = PROPS(29)
      Tm     = PROPS(30)
      ! yTS  = (1-(T*)^m)
      ! T*   = (T-Tr)/(Tm-Tr)
      IF ((Temp .le. Tr).or.(m.eq.ZERO)) THEN
        yTS = ONE
        HTS = ZERO
        ELSE
        Tstar = (Temp-Tr)/(Tm-Tr)
        yTS = ONE - Tstar**m
        HTS = -ONE/(Tm-Tr)*m*Tstar**(m-ONE)
      ENDIF
      RETURN
      END

      SUBROUTINE LODE_K2(MU,LODE,g,Lk)
      IMPLICIT DOUBLE PRECISION (A-Z)
      REAL*8 MU, LODE, g, Lk
      ZERO = 0.D0
      ONE=1.D0
      IF (LODE.eq.ZERO) THEN
        MU = g + ( ONE - g)
        ELSE
        MU = g + ( ONE - g) * ( dabs(LODE) )**Lk
      ENDIF
      RETURN
      END

      SUBROUTINE FC_HC(EQPSf,TRIAX,LODE,PROPS)
      IMPLICIT DOUBLE PRECISION (A-Z)
      DIMENSION PROPS(*)
      REAL*8 Dold, Dnew, dD, EQPSf, TRIAX, LODE
      REAL*8 a, b, c, n, f1, f2, f3, PI
      PARAMETER (ZERO = 0.D0, HALF = 0.5D0, ONE  = 1.D0, OP5 = 1.5D0, 
     1           TWO = 2.D0, THREE = 3.D0, SIX = 6.D0)
      PI = DACOS(-ONE)
      a = PROPS(33)
      b = PROPS(34)
      c = PROPS(35)
      n = PROPS(36)
      f1 =  (TWO/THREE)*DCOS((PI/SIX)*(ONE-LODE))
      f2 =  (TWO/THREE)*DCOS((PI/SIX)*(THREE+LODE))
      f3 = -(TWO/THREE)*DCOS((PI/SIX)*(ONE+LODE))
      EQPSf = (b*(ONE+c)**(ONE/n))*
     1        ((((HALF*
     2        (((f1-f2)**a)+((f2-f3)**a)+((f1-f3)**a)))**(ONE/a))+
     3        c*(TWO*TRIAX+f1+f3))**(-ONE/n))
      RETURN
      END

      SUBROUTINE FC_JCX(EQPSf,TRIAX,LODE,PROPS)
      IMPLICIT DOUBLE PRECISION (A-Z)
      DIMENSION PROPS(*)
      REAL*8 Dold, Dnew, dD, EQPSf, TRIAX, LODE
      REAL*8 D1, D2, D3, D4, D5, gF, MUf, Lk
      Lk = PROPS(46)
      D1 = PROPS(33)
      D2 = PROPS(34)
      D3 = PROPS(35)
      gF = PROPS(36)
      CALL LODE_K2(MUf,LODE,gf,Lk)
      EQPSf = (D1+D2*dEXP(D3*TRIAX))*MUf
      RETURN
      END

      SUBROUTINE D_CL(Dnew,WclNew,Dold,WclOld,SIGMA1,deqps,PROPS)
      INCLUDE 'VABA_PARAM.INC'
      DIMENSION PROPS(*)
      REAL*8 SIGMA1, deqps
      REAL*8 Dnew, Dold, WCR, WclNew, WclOld, dWcl,dD
      WCR   = PROPS(33)
      DcMax = PROPS(44)
      dWcl = SIGMA1*deqps
      dD = dWcl/WCR
      WclNew = WclOld + dWcl
      Dnew = Dold + dD
        IF (Dnew .gt. DcMax) THEN
        Dnew = DcMax
        ENDIF
      RETURN
      END

      SUBROUTINE STRAIN_RATE_FAIL(fSR,eqpsDot,PROPS)
      INCLUDE 'VABA_PARAM.INC'
      DIMENSION PROPS(*)
      REAL*8 fSR, D4, eqpsdot, eps0
      ZERO = 0.D0
      ONE  = 1.D0
      ! fSR  = 1+D4*ln(EQPSDot/eps0)
      Eps0  = PROPS(25)
      D4 = PROPS(37)
      IF ((D4.eq.ZERO).or.(eqpsdot .le. Eps0)) THEN
        fSR = ONE
        ELSE
        fSR = ONE + D4*dlog(eqpsDot/Eps0)
      ENDIF
      RETURN
      END

      SUBROUTINE THERMAL_SOFT_FAIL(fTS,Temp,PROPS)
      INCLUDE 'VABA_PARAM.INC'
      DIMENSION PROPS(*)
      REAL*8 fTS, Temp, T0, Tr, Tm, Tstar, D5
      ZERO = 0.D0
      ONE  = 1.D0
      T0     = PROPS(28)
      Tr     = PROPS(29)
      Tm     = PROPS(30)
      D5     = PROPS(38)
      ! fTS  =  1+D5(T*)
      ! T*   = (T-Tr)/(Tm-Tr)
      IF ((Temp .le. Tr).or.(D5.eq.ZERO)) THEN
        fTS = ONE
        ELSE
        Tstar = (Temp-Tr)/(Tm-Tr)
        fTS = ONE - D5*Tstar
      ENDIF
      RETURN
      END

      SUBROUTINE D_LINEAR(Dnew,Dold,EQPSf,deqps,PROPS)
      INCLUDE 'VABA_PARAM.INC'
      DIMENSION PROPS(*)
      REAL*8 Dold, Dnew, dD, deqps, ONE
      ZERO = 0.D0
      ONE  = 1.D0
      DcMax = PROPS(44)
      dD = dmax1(ZERO, (ONE/EQPSf)*deqps)
      Dnew = Dold + dD
        IF (Dnew .gt. DcMax) THEN
        Dnew = DcMax
        ENDIF
      RETURN
      END

      SUBROUTINE SOFT(beta,Hbeta,D,PROPS)
      INCLUDE 'VABA_PARAM.INC'
      DIMENSION PROPS(*)
      REAL*8 beta, Hbeta, D, D0, Dc, mD, ONE
      D0 = PROPS(41)
      Dc = PROPS(42)
      mD = PROPS(43)
      ONE  = 1.D0
      ZERO = 0.D0
      IF ((D.LE.D0).or.(mD.eq.ZERO)) THEN
        beta = ONE
        Hbeta = ZERO
        else
        beta = ((Dc-D)/(Dc-D0))**mD
        Hbeta = (mD/(D0-Dc))*((Dc-D)/(Dc-D0))**(mD-ONE)
      END IF
      RETURN
      END

!     +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
!     +           Compute eigenvalues of the Stress Tensor            +
!     +                    sigma1,sigma2,sigma3                       +
!     +           ( Q.-C. He, C. Vall´ee and C. Lerintiu)             +
!     +            Z. angew. Math. Phys. 56 (2005) 357–366            +
!     +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
      SUBROUTINE EIGENVALUES(
     1           PRINCIPAL1,PRINCIPAL2,PRINCIPAL3,
     2           SIGMA1,SIGMA2,SIGMA3,SIGMA4,SIGMA5,SIGMA6)
      IMPLICIT DOUBLE PRECISION (A-Z)
      REAL*8 PRINCIPAL1,PRINCIPAL2,PRINCIPAL3,LODEFUNC
      REAL*8 SIGMA1,SIGMA2,SIGMA3,SIGMA4,SIGMA5,SIGMA6
      REAL*8 SQSIGMA1,SQSIGMA2,SQSIGMA3,I1,I2,I3,FF,GG,HH,WW
      PI=acos(-1.)

      SQSIGMA1=SIGMA1*SIGMA1+SIGMA4*SIGMA4+SIGMA6*SIGMA6
      SQSIGMA2=SIGMA4*SIGMA4+SIGMA2*SIGMA2+SIGMA5*SIGMA5
      SQSIGMA3=SIGMA6*SIGMA6+SIGMA5*SIGMA5+SIGMA3*SIGMA3
c     Invariants of the Stress tensor(I1,I2,I3)
      I1=SIGMA1+SIGMA2+SIGMA3
      I2=1./2.*(I1*I1-(SQSIGMA1+SQSIGMA2+SQSIGMA3))
      I3=SIGMA1*(SIGMA2*SIGMA3-SIGMA5*SIGMA5)+
     1   SIGMA4*(SIGMA5*SIGMA6-SIGMA3*SIGMA4)+
     2   SIGMA6*(SIGMA4*SIGMA5-SIGMA2*SIGMA5)
c     Compute eigenvalues of TENSOR
c     PRINCIPAL1>PRINCIPAL2>PRINCIPAL3
      ff= 2.*I1*I1*I1-9.*I1*I2+27.*I3
      gg= I1*I1-3.*I2
!     1st case PRINCIPAL1=PRINCIPAL2=PRINCIPAL3 g=0
      if (gg.le.0.) then
        PRINCIPAL1=1./3.*I1
        PRINCIPAL2=1./3.*I1
        PRINCIPAL3=1./3.*I1
        else
        hh=ff/(2.*(gg)**(3./2.))
      endif
!     2nd case PRINCIPAL1=PRINCIPAL2>PRINCIPAL3 h=-1; w=PI/3
      if(hh.le.-1.)then
        ww=1./3.*acos(-1.)
        PRINCIPAL1=1./3.*I1+1./3.*sqrt(abs(I1*I1-3.*I2))
        PRINCIPAL2=1./3.*I1+1./3.*sqrt(abs(I1*I1-3.*I2))
        PRINCIPAL3=1./3.*I1-2./3.*sqrt(abs(I1*I1-3.*I2))
!     3rd case PRINCIPAL1>PRINCIPAL2=PRINCIPAL3 h=1; w=0
        elseif(hh.ge.1.)then
        ww=1./3.*acos(1.)
        PRINCIPAL1=1./3.*I1+2./3.*sqrt(abs(I1*I1-3.*I2))
        PRINCIPAL2=1./3.*I1-1./3.*sqrt(abs(I1*I1-3.*I2))
        PRINCIPAL3=1./3.*I1-1./3.*sqrt(abs(I1*I1-3.*I2))
!     4th case PRINCIPAL1>PRINCIPAL2>PRINCIPAL3
        else
        ww=1./3.*acos(hh)
        PRINCIPAL1=1./3.*I1+2./3.*sqrt(abs(I1*I1-3.*I2))*cos(ww)
        PRINCIPAL2=1./3.*I1+2./3.*sqrt(abs(I1*I1-3.*I2))*
     1             cos(2./3.*PI-ww)
        PRINCIPAL3=1./3.*I1+2./3.*sqrt(abs(I1*I1-3.*I2))*
     1             cos(2./3.*PI+ww)
      endif
      PRINCIPAL1=max(PRINCIPAL1,PRINCIPAL2,PRINCIPAL3)
      PRINCIPAL3=min(PRINCIPAL1,PRINCIPAL2,PRINCIPAL3)
      PRINCIPAL2=I1-PRINCIPAL1-PRINCIPAL3
      RETURN
      END
!     +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++