#!/usr/bin/env bash

CONFIG_SRC="wct-sim-nf-sp-img-bdf-points.jsonnet"
BASE_RESULT_DIR="/nfs/data/1/yujin/img_BlobDepoFill/pdhd-wct-sim/05132026_point_depo_multi_scan_modified_subset"
mkdir -p "${BASE_RESULT_DIR}"

# --- 좌표 리스트 설정 (확장성 확보) ---
# 특정 좌표만 고정하고 싶으면 리스트에 값을 하나만 적으세요.
X_LIST=(10 30 50 70 90 110 130 150 170 190 210 230 250 270 300 310 330)
# X_LIST=(20 40 60 80 100 110 120 130 140 160 180 200 220 240 260 280 290 300 320 340 )
Y_LIST=(300)
Z_LIST=(100)

echo ">>> Starting Multi-Dimensional Scan..."
echo ">>> Targets - X: [${X_LIST[*]}], Y: [${Y_LIST[*]}], Z: [${Z_LIST[*]}]"

# ——————————————————————————————
# 3중 중첩 루프 (X -> Y -> Z)
# ——————————————————————————————
run_num=1
for rx in "${X_LIST[@]}"; do
    for ry in "${Y_LIST[@]}"; do
        for rz in "${Z_LIST[@]}"; do

            # 폴더명 및 태그 생성
            TAG="X${rx}_Y${ry}_Z${rz}"
            SUB_DIR="${BASE_RESULT_DIR}/${TAG}"
            mkdir -p "${SUB_DIR}"

            echo "================================================"
            echo ">>> [RUN #${run_num}] Position: (${rx}, ${ry}, ${rz})"
            echo ">>> Directory: ${SUB_DIR}"
            echo "================================================"

            # 1) 임시 Jsonnet 설정 파일 생성
            TMP_CFG="tmp_cfg_${TAG}.jsonnet"
            sed -e "s|^local point_x = .*|local point_x = ${rx};|" \
                -e "s|^local point_y = .*|local point_y = ${ry};|" \
                -e "s|^local point_z = .*|local point_z = ${rz};|" \
                "${CONFIG_SRC}" > "${TMP_CFG}"

            # 2) Wire-Cell 실행 및 로그 기록 (tee 활용)
            LOG_FILE="wirecell_sim_${TAG}.log"
            wire-cell -L debug -l stdout "${TMP_CFG}" --ext-code "elecGain=14" 2>&1 | tee "${LOG_FILE}"

            # 3) 결과 파일 이동
            mv "${LOG_FILE}" "${SUB_DIR}/"
            mv clusters-apa-*.tar.gz "${SUB_DIR}/" 2>/dev/null || true
            mv depos-drifted-*.zip "${SUB_DIR}/" 2>/dev/null || true
            
            if [[ -f "pdhd-sim-check-deposplat.root" ]]; then
                mv "pdhd-sim-check-deposplat.root" "${SUB_DIR}/pdhd_sim_${TAG}.root"
            fi

            # 4) 임시 파일 삭제
            rm -f "${TMP_CFG}"

            ((run_num++))
        done
    done
done

echo "================================================"
echo "All scans completed! Total runs: $((run_num - 1))"