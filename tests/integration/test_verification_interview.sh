#!/bin/bash
# Integration test for verification interview feature

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Verification Interview Integration Test ==="

# Test 1: Checkpoint detection
echo ""
echo "Test 1: Checkpoint Detection"
echo "----------------------------"

# Create mock test data
TEST_DIR="$PROJECT_ROOT/tests/mock-recording"
mkdir -p "$TEST_DIR/recording/screenshots"

# Mock touch events
cat > "$TEST_DIR/recording/touch_events.json" << 'EOF'
[
  {"timestamp": 0.0, "x": 500, "y": 1000, "gesture_type": "tap"},
  {"timestamp": 2.5, "x": 600, "y": 800, "gesture_type": "tap"},
  {"timestamp": 15.0, "x": 100, "y": 100, "gesture_type": "tap"},
  {"timestamp": 16.0, "x": 500, "y": 2200, "gesture_type": "tap"}
]
EOF

# Create mock screenshots (would be real in actual recording)
# For test, just create empty images
for i in {1..4}; do
    touch "$TEST_DIR/recording/screenshots/touch_$(printf "%03d" $i).png"
done

echo "✓ Mock test data created"

# Run checkpoint detection
if python3 "$PROJECT_ROOT/scripts/analyze-checkpoints.py" "$TEST_DIR" > "$TEST_DIR/recording/checkpoints.json" 2>/dev/null; then
    echo "✓ Checkpoint detection executed"

    # Verify output format
    if jq -e '.checkpoints | length > 0' "$TEST_DIR/recording/checkpoints.json" > /dev/null 2>&1; then
        echo "✓ Checkpoints detected"
    else
        echo "✗ No checkpoints in output"
        exit 1
    fi
else
    echo "✗ Checkpoint detection failed"
    exit 1
fi

# Test 2: YAML generation
echo ""
echo "Test 2: YAML Generation"
echo "-----------------------"

# Create mock verifications
cat > "$TEST_DIR/recording/verifications.json" << 'EOF'
{
  "verifications": [
    {
      "touch_index": 2,
      "type": "screen",
      "description": "Back button worked"
    }
  ]
}
EOF

# Generate YAML
if python3 "$PROJECT_ROOT/scripts/generate-test.py" "$TEST_DIR" "com.test.app" "mock-test" > /dev/null 2>&1; then
    echo "✓ YAML generation executed"

    # Verify YAML created
    if [ -f "$TEST_DIR/test.yaml" ]; then
        echo "✓ test.yaml created"

        # Verify verification inserted
        if grep -q "verify_screen" "$TEST_DIR/test.yaml"; then
            echo "✓ Verification inserted"
        else
            echo "✗ Verification not found in YAML"
            exit 1
        fi
    else
        echo "✗ test.yaml not created"
        exit 1
    fi
else
    echo "✗ YAML generation failed"
    exit 1
fi

# Cleanup
rm -rf "$TEST_DIR"

echo ""
echo "=== All Tests Passed ==="
