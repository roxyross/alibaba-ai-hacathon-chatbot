#!/bin/bash
# Deploy ROXY AI Backend to Hugging Face Space
# Usage: ./deploy-hf-space.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SPACE_ID="Rijji/roxy-personal-ai"
HF_TOKEN=${HF_TOKEN:-""}

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         ROXY AI — Hugging Face Space Deploy            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check for HF token
if [ -z "$HF_TOKEN" ]; then
    echo -e "${YELLOW}⚠  HF_TOKEN not set. You can:${NC}"
    echo "  1. Set it: export HF_TOKEN=hf_xxxx"
    echo "  2. Or clone/push manually"
    echo ""
fi

# Clone the Space
echo -e "${YELLOW}→ Cloning Space: ${SPACE_ID}${NC}"
rm -rf /tmp/roxy-space
git clone https://huggingface.co/spaces/${SPACE_ID} /tmp/roxy-space

# Copy backend files
echo -e "${YELLOW}→ Copying backend files...${NC}"
rm -rf /tmp/roxy-space/src
cp -r huggingface-space-roxy-hub/src /tmp/roxy-space/
cp huggingface-space-roxy-hub/app.py /tmp/roxy-space/
cp huggingface-space-roxy-hub/requirements.txt /tmp/roxy-space/

# Update app.py to use the correct Space ID
sed -i 's/rijji-roxy-personal-ai/Rijji-roxy-personal-ai/g' /tmp/roxy-space/app.py

# Push back
cd /tmp/roxy-space
echo -e "${YELLOW}→ Pushing to Hugging Face Space...${NC}"

if [ -n "$HF_TOKEN" ]; then
    git push https://huggingface.co/spaces/${SPACE_ID} main
else
    git push https://huggingface.co/${SPACE_ID} main
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Deployment initiated!${NC}"
echo ""
echo "Your Space: https://huggingface.co/spaces/${SPACE_ID}"
echo "It will rebuild automatically..."
echo ""
