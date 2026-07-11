#!/usr/bin/env bash

CONFIG_SRC="wct-sim-nf-sp-img-bdf-points.jsonnet"
BASE_RESULT_DIR="/nfs/data/1/yujin/img_BlobDepoFill/pdhd-wct-sim/point_depo_localized_sphere_25/"
mkdir -p "${BASE_RESULT_DIR}"

# 1. 중심 좌표 리스트 (단위: mm)
X_CENTERS=(60 170 280)
Y_CENTERS=(100 300 500)      # 나중 확장을 위해 리스트로 처리
Z_CENTERS=(60 115 170)

# 2. 구 내부 격자 설정 (단위: mm)
RADIUS=50           # 반지름 10cm = 100mm
STEP=25              # 간격 2cm = 20mm

echo ">>> Starting 3D Sphere Point Depo Scan..."
echo ">>> Radius: ${RADIUS}mm, Step: ${STEP}mm"

# ——————————————————————————————
# 중심 좌표 루프 (X, Y, Z)
# ——————————————————————————————
for cx in "${X_CENTERS[@]}"; do
for cy in "${Y_CENTERS[@]}"; do
for cz in "${Z_CENTERS[@]}"; do

    # 중심별 부모 폴더 생성
    POS_DIR="${BASE_RESULT_DIR}/center_X${cx}_Y${cy}_Z${cz}"
    mkdir -p "${POS_DIR}"

    echo "================================================"
    echo ">>> Target Center: (${cx}, ${cy}, ${cz})"
    echo "================================================"

    # ——————————————————————————————
    # 구 내부 격자 루프 (Relative to Center)
    # ——————————————————————————————
    # -RADIUS부터 +RADIUS까지 STEP 간격으로 탐색
    run_idx=1
    for (( dx=-RADIUS; dx<=RADIUS; dx+=STEP )); do
    for (( dy=-RADIUS; dy<=RADIUS; dy+=STEP )); do
    for (( dz=-RADIUS; dz<=RADIUS; dz+=STEP )); do

    # 중심으로부터의 거리 계산 (Euclidean distance)
        # Bash는 부동소수점 연산이 약하므로 정수 제곱합으로 비교 (d^2 <= R^2)
        DIST_SQ=$(( dx*dx + dy*dy + dz*dz ))
        RADIUS_SQ=$(( RADIUS*RADIUS ))

        if [ $DIST_SQ -le $RADIUS_SQ ]; then
            # 실제 절대 좌표 계산
            real_x=$(( cx + dx ))
            real_y=$(( cy + dy ))
            real_z=$(( cz + dz ))

            TAG="X${real_x}_Y${real_y}_Z${real_z}"
            SUB_DIR="${POS_DIR}/run_point_${TAG}"
            mkdir -p "${SUB_DIR}"

            echo ">>> [RUN] Dist:$(( DIST_SQ )) <= $(( RADIUS_SQ )) | Pos: (${real_x}, ${real_y}, ${real_z}) -> ${SUB_DIR}"

            # 1) 임시 Jsonnet 설정 파일 생성 (sed 치환)
            TMP_CFG="tmp_cfg_${TAG}.jsonnet"
            sed -e "s|^local point_x = .*|local point_x = ${real_x};|" \
                -e "s|^local point_y = .*|local point_y = ${real_y};|" \
                -e "s|^local point_z = .*|local point_z = ${real_z};|" \
                "${CONFIG_SRC}" > "${TMP_CFG}"

            # 2) Wire-Cell 실행
            wire-cell -L debug -l stdout "${TMP_CFG}" --ext-code "elecGain=14"

            # 3) 결과 파일 이동
            mv clusters-apa-*.tar.gz "${SUB_DIR}/" 2>/dev/null || true
            mv depos-drifted-*.zip "${SUB_DIR}/" 2>/dev/null || true
            
            if [[ -f "pdhd-sim-check-deposplat.root" ]]; then
                mv "pdhd-sim-check-deposplat.root" "${SUB_DIR}/pdhd_sim_${TAG}.root"
            fi

            # 4) 임시 파일 삭제
            rm -f "${TMP_CFG}"
            
            ((run_idx++))
        fi
    done
    done
    done
done
done
done

echo "================================================"
echo "Sphere Grid Scan Completed!"