#!/usr/bin/env bash

# ——————————————————————————————
# 1. 환경 및 스캔 범위 설정
# ——————————————————————————————
CONFIG_SRC="wct-sim-nf-sp-img-bdf-points.jsonnet"
MAIN_RESULT_DIR="/nfs/data/1/yujin/img_BlobDepoFill/pdhd-wct-sim/point_depo_scan_find_grid/"
mkdir -p "${MAIN_RESULT_DIR}"

X_START=10; X_END=340; X_STEP=60
Y_START=10;  Y_END=590; Y_STEP=100
Z_START=10; Z_END=200; Z_STEP=40

echo ">>> Starting 3D Point Depo Scan..."
echo ">>> Results will be stored in: ${MAIN_RESULT_DIR}"

# ——————————————————————————————
# 2. 3중 루프 실행 (X -> Y -> Z)
# ——————————————————————————————
for (( x=$X_START; x<=$X_END; x+=$X_STEP )); do
    for (( y=$Y_START; y<=$Y_END; y+=$Y_STEP )); do
        for (( z=$Z_START; z<=$Z_END; z+=$Z_STEP )); do

            TAG="X${x}_Y${y}_Z${z}"
            SUB_DIR="${MAIN_RESULT_DIR}/run_${TAG}"
            mkdir -p "${SUB_DIR}"

            echo "------------------------------------------------"
            echo ">>> Running: (${x}, ${y}, ${z}) | Target: ${SUB_DIR}"

            # 1) 임시 Jsonnet 설정 파일 생성
            TMP_CFG="tmp_cfg_${TAG}.jsonnet"

            # sed를 이용해 local 변수 선언 줄을 현재 루프의 값으로 교체
            # 주의: 원본 파일에 'local point_x = ...' 형식이 있어야 함
            sed -e "s|^local point_x = .*|local point_x = ${x};|" \
                -e "s|^local point_y = .*|local point_y = ${y};|" \
                -e "s|^local point_z = .*|local point_z = ${z};|" \
                "${CONFIG_SRC}" > "${TMP_CFG}"

            # 2) Wire-Cell 실행
            /usr/bin/time -v wire-cell -L debug -l stdout "${TMP_CFG}" --ext-code "elecGain=14"

            # 3) 생성된 파일들을 결과 디렉토리로 이동
            # 파일 패턴에 맞춰 mv 실행
            mv clusters-apa-*.tar.gz "${SUB_DIR}/" 2>/dev/null || true
            mv depos-drifted-*.zip "${SUB_DIR}/" 2>/dev/null || true
            
            # 고정된 이름의 ROOT 파일 이동
            if [[ -f "pdhd-sim-check-deposplat.root" ]]; then
                mv "pdhd-sim-check-deposplat.root" "${SUB_DIR}/pdhd_sim_${TAG}.root"
            fi

            # 4) 임시 파일 삭제
            rm -f "${TMP_CFG}"

            echo ">>> [DONE] Results saved to ${SUB_DIR}"

        done
    done
done

echo "================================================"
echo "All 3D Scans Completed! Check: ${MAIN_RESULT_DIR}"