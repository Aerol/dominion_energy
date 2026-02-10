#!/bin/bash

# Dominion Energy Integration - Auto Deploy Script
# This script commits and pushes changes to GitHub for HACS

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Dominion Energy Integration Deployer${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}Error: Not in a git repository!${NC}"
    echo "Please run this script from your GitHub repository directory."
    exit 1
fi

# Check if there are changes to commit
if git diff-index --quiet HEAD --; then
    echo -e "${YELLOW}No changes to commit.${NC}"
    exit 0
fi

# Get current version from manifest.json
CURRENT_VERSION=$(grep -o '"version": "[^"]*' custom_components/dominion_energy/manifest.json | cut -d'"' -f4)
echo -e "Current version: ${YELLOW}${CURRENT_VERSION}${NC}"

# Prompt for new version
echo ""
echo "Enter new version (or press Enter to keep ${CURRENT_VERSION}):"
read NEW_VERSION

if [ -z "$NEW_VERSION" ]; then
    NEW_VERSION=$CURRENT_VERSION
    echo -e "Keeping version: ${YELLOW}${NEW_VERSION}${NC}"
else
    # Update version in manifest.json
    sed -i.bak "s/\"version\": \"${CURRENT_VERSION}\"/\"version\": \"${NEW_VERSION}\"/" custom_components/dominion_energy/manifest.json
    rm -f custom_components/dominion_energy/manifest.json.bak
    echo -e "Updated version to: ${GREEN}${NEW_VERSION}${NC}"
fi

# Show what will be committed
echo ""
echo -e "${YELLOW}Changes to be committed:${NC}"
git status --short

# Generate commit message
COMMIT_MSG="Release v${NEW_VERSION}

Updates:
- Full 2FA authentication with Gigya
- Automatic token refresh every 30 minutes
- Cookie persistence for 2FA bypass
- Dual data sources (Excel + Green Button XML)
- Separate daily (yesterday) and monthly usage sensors
- Account/meter number configuration
- Production-ready error handling

Data Sources:
- Primary: Green Button XML (official utility billing data)
- Fallback: Excel export
- Auto-comparison and selection of most accurate data

Sensors:
- Yesterday Usage (complete day data)
- Monthly Usage (month-to-date)
- Last Hour Usage
- Estimated Cost
- Account Number
- Meter Number"

# Show commit message
echo ""
echo -e "${YELLOW}Commit message:${NC}"
echo "$COMMIT_MSG"
echo ""

# Confirm
echo -e "${YELLOW}Proceed with commit and push? (y/n):${NC}"
read -r CONFIRM

if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo -e "${RED}Aborted.${NC}"
    exit 1
fi

# Add all files in custom_components/dominion_energy/
git add custom_components/dominion_energy/

# Commit
echo ""
echo -e "${GREEN}Committing changes...${NC}"
git commit -m "$COMMIT_MSG"

# Get current branch
BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo -e "Current branch: ${YELLOW}${BRANCH}${NC}"

# Push
echo ""
echo -e "${GREEN}Pushing to origin/${BRANCH}...${NC}"
git push origin "$BRANCH"

# Create git tag for the version
echo ""
echo -e "${GREEN}Creating tag v${NEW_VERSION}...${NC}"
if git rev-parse "v${NEW_VERSION}" >/dev/null 2>&1; then
    echo -e "${YELLOW}Tag v${NEW_VERSION} already exists, skipping tag creation${NC}"
else
    git tag -a "v${NEW_VERSION}" -m "Release version ${NEW_VERSION}"
    git push origin "v${NEW_VERSION}"
    echo -e "${GREEN}Tag v${NEW_VERSION} created and pushed!${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Successfully deployed v${NEW_VERSION}!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Verify the commit on GitHub"
echo "2. HACS will detect the new version automatically"
echo "3. Users can update via HACS interface"
echo ""
