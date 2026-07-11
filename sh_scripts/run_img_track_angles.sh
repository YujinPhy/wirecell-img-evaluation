#!/usr/bin/env bash

CONFIG_SRC="wct-sim-nf-sp-img-bdf-tracks.jsonnet"
BASE_RESULT_DIR="/nfs/data/1/yujin/img_BlobDepoFill/pdhd-wct-sim/tracks/tracks_angle_at_x_10"
mkdir -p "${BASE_RESULT_DIR}"

# 1. 스캔 파라미터 설정
THETA_LIST=(0 10 20 30 40 50 60 70 80 85)
FIXED_L=50  # 고정할 트랙 길이 (단위: cm)

echo ">>> Starting Angle Scan with Constant Track Length: ${FIXED_L} cm"

for ang in "${THETA_LIST[@]}"; do
    # 결과 폴더 이름 (각도와 길이를 모두 표시)
    SUB_DIR="${BASE_RESULT_DIR}/run_theta${ang}_L${FIXED_L}"
    mkdir -p "${SUB_DIR}"

    echo "------------------------------------------------"
    echo ">>> [EXEC] Angle: ${ang} deg | Length: ${FIXED_L} cm"

    # 1) 임시 Jsonnet 설정 파일 생성
    # angleXZ_deg와 track_L 두 라인을 모두 찾아 바꿉니다.
    TMP_CFG="tmp_cfg_angle${ang}.jsonnet"
    
    sed -e "s|^local angleXZ_deg = .*|local angleXZ_deg = ${ang};|" \
        -e "s|^local track_L = .*|local track_L = ${FIXED_L};|" \
        "${CONFIG_SRC}" > "${TMP_CFG}"

    # 2) Wire-Cell 실행
    wire-cell -L debug -l stdout "${TMP_CFG}" --ext-code "elecGain=14"

    # 3) 결과 파일 이동
    mv clusters-apa-*.tar.gz "${SUB_DIR}/" 2>/dev/null
    mv clusters-bdf-apa-*.tar.gz "${SUB_DIR}/" 2>/dev/null
    mv depos-drifted-*.zip "${SUB_DIR}/" 2>/dev/null
    
    if [[ -f "pdhd-sim-check-deposplat.root" ]]; then
        mv "pdhd-sim-check-deposplat.root" "${SUB_DIR}/pdhd_sim_theta${ang}.root"
    fi

    # 4) 임시 파일 삭제
    rm -f "${TMP_CFG}"
    echo ">>> [DONE] Angle ${ang} finished."
done

echo "================================================"
echo ">>> Angle & Length Scan Completed!"