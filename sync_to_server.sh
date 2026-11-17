#!/bin/bash
# 同步免费节点 hub 到 6ix9ine 服务器（/nodes/），主页已指向站内。
# 同步 data/（当日文件 + index.json）与 nodes/ 当日快照（rsync 只传变化部分）。
set -e
cd "$(dirname "$0")"
BASE=/opt/web-platform/applications/nodes
rsync -rlptz --chmod=a+rX -e "ssh -F $HOME/.ssh/config" data/ --rsync-path="sudo rsync" 6ix9ine:$BASE/data/
rsync -rlptz --chmod=a+rX -e "ssh -F $HOME/.ssh/config" nodes/ --rsync-path="sudo rsync" 6ix9ine:$BASE/nodes/
TODAY=$(TZ=Asia/Shanghai date +%F)
ssh -F $HOME/.ssh/config 6ix9ine "grep -q $TODAY $BASE/data/index.json && echo SYNC_OK $TODAY || { echo SYNC_FAIL $TODAY; exit 1; }"
