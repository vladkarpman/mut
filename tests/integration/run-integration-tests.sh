#!/bin/bash

# Integration Test Runner for Mobile UI Testing Plugin
# Tests all commands and conditional operators with Android Calculator

set -e  # Exit on first error

echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Mobile UI Testing Plugin - Integration Tests            ║"
echo "╔════════════════════════════════════════════════════════════╗"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Function to print test result
print_result() {
    local test_name="$1"
    local result="$2"
    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if [ "$result" = "PASS" ]; then
        echo -e "${GREEN}✓${NC} $test_name"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}✗${NC} $test_name"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

# ============================================================
# Phase 1: Prerequisites Check
# ============================================================

echo "─────────────────────────────────────────────────────────────"
echo "Phase 1: Checking Prerequisites"
echo "─────────────────────────────────────────────────────────────"
echo ""

# Check adb
echo -n "Checking adb... "
if command -v adb &> /dev/null; then
    echo -e "${GREEN}OK${NC}"
    print_result "adb installed" "PASS"
else
    echo -e "${RED}FAIL${NC}"
    print_result "adb installed" "FAIL"
    echo "Error: adb not found. Please install Android SDK platform-tools."
    exit 1
fi

# Check device connected
echo -n "Checking device connection... "
DEVICE_COUNT=$(adb devices | grep -v "List" | grep "device$" | wc -l | tr -d ' ') || DEVICE_COUNT=0
if [ "$DEVICE_COUNT" -gt 0 ]; then
    echo -e "${GREEN}OK${NC} ($DEVICE_COUNT device(s))"
    print_result "Device connected" "PASS"
else
    echo -e "${RED}FAIL${NC}"
    print_result "Device connected" "FAIL"
    echo "Error: No devices connected. Run 'adb devices' to check."
    exit 1
fi

# Check Calculator app
echo -n "Checking Calculator app... "
if adb shell pm list packages | grep -q calculator; then
    CALC_PACKAGE=$(adb shell pm list packages | grep calculator | head -1 | cut -d: -f2 | tr -d '\r\n')
    echo -e "${GREEN}OK${NC} ($CALC_PACKAGE)"
    print_result "Calculator app present" "PASS"
else
    echo -e "${RED}FAIL${NC}"
    print_result "Calculator app present" "FAIL"
    echo "Error: Calculator app not found on device."
    exit 1
fi

# Check ffmpeg (for recording tests)
echo -n "Checking ffmpeg... "
if command -v ffmpeg &> /dev/null; then
    echo -e "${GREEN}OK${NC}"
    print_result "ffmpeg installed" "PASS"
else
    echo -e "${YELLOW}WARNING${NC} - Recording tests will be skipped"
    print_result "ffmpeg installed" "FAIL"
fi

echo ""

# ============================================================
# Phase 2: Command Testing
# ============================================================

echo "─────────────────────────────────────────────────────────────"
echo "Phase 2: Command Testing"
echo "─────────────────────────────────────────────────────────────"
echo ""

# Test 1: /create-test
echo "Test 1: /create-test command"
echo "   Expected: Creates test file with proper structure"
echo "   Action: Manual verification required"
echo -e "   ${YELLOW}→ Run: /create-test calculator-test-manual${NC}"
echo "   → Verify: tests/calculator-test-manual/test.yaml exists"
echo ""
read -p "   Did /create-test work correctly? (y/n): " response
response=$(echo "$response" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
case "$response" in
    y|yes)
        print_result "/create-test command" "PASS"
        ;;
    *)
        print_result "/create-test command" "FAIL"
        ;;
esac
echo ""

# Test 2: /generate-test
echo "Test 2: /generate-test command"
echo "   Expected: Generates valid YAML from natural language"
echo "   Action: Manual verification required"
echo -e "   ${YELLOW}→ Run: /generate-test \"tap 2, tap plus, tap 2, tap equals\"${NC}"
echo "   → Verify: Valid YAML generated with correct actions"
echo ""
read -p "   Did /generate-test work correctly? (y/n): " response
response=$(echo "$response" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
case "$response" in
    y|yes)
        print_result "/generate-test command" "PASS"
        ;;
    *)
        print_result "/generate-test command" "FAIL"
        ;;
esac
echo ""

# Test 3: /run-test
echo "Test 3: /run-test command"
echo "   Expected: Executes test files successfully"
echo "   Action: Automated test execution"
echo -e "   ${YELLOW}→ Running: tests/integration/calculator/basic-operations.test.yaml${NC}"
echo ""
read -p "   Ready to run /run-test? (y to continue): " response
response=$(echo "$response" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
case "$response" in
    y|yes)
        echo "   → Please run: /run-test tests/integration/calculator/basic-operations.test.yaml"
        read -p "   Did the test execute and pass? (y/n): " result
        result=$(echo "$result" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
        case "$result" in
            y|yes)
                print_result "/run-test basic operations" "PASS"
                ;;
            *)
                print_result "/run-test basic operations" "FAIL"
                ;;
        esac
        ;;
esac
echo ""

# Test 4: /record-test and /stop-recording
if command -v ffmpeg &> /dev/null; then
    echo "Test 4: /record-test and /stop-recording commands"
    echo "   Expected: Records touch events and generates test"
    echo "   Action: Manual verification required"
    echo -e "   ${YELLOW}→ Run: /record-test calculator-recording${NC}"
    echo "   → Perform: Tap 5, tap +, tap 3, tap ="
    echo -e "   ${YELLOW}→ Run: /stop-recording${NC}"
    echo "   → Verify: test.yaml created with element text (not coordinates)"
    echo ""
    read -p "   Did recording work correctly? (y/n): " response
    response=$(echo "$response" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
    case "$response" in
        y|yes)
            print_result "/record-test and /stop-recording" "PASS"
            ;;
        *)
            print_result "/record-test and /stop-recording" "FAIL"
            ;;
    esac
fi
echo ""

# ============================================================
# Phase 3: Conditional Operators Testing
# ============================================================

echo "─────────────────────────────────────────────────────────────"
echo "Phase 3: Conditional Operators Testing"
echo "─────────────────────────────────────────────────────────────"
echo ""

echo "Test 5: Conditional operators"
echo "   Expected: All 5 operators work with proper branching"
echo -e "   ${YELLOW}→ Running: tests/integration/calculator/conditional-logic.test.yaml${NC}"
echo ""
read -p "   Ready to run conditional tests? (y to continue): " response
response=$(echo "$response" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
case "$response" in
    y|yes)
        echo "   → Please run: /run-test tests/integration/calculator/conditional-logic.test.yaml"
        echo ""
        read -p "   Did if_exists work correctly? (y/n): " result
        result=$(echo "$result" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
        if [ "$result" = "y" ] || [ "$result" = "yes" ]; then
            print_result "if_exists operator" "PASS"
        else
            print_result "if_exists operator" "FAIL"
        fi

        read -p "   Did if_not_exists work correctly? (y/n): " result
        result=$(echo "$result" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
        if [ "$result" = "y" ] || [ "$result" = "yes" ]; then
            print_result "if_not_exists operator" "PASS"
        else
            print_result "if_not_exists operator" "FAIL"
        fi

        read -p "   Did if_all_exist work correctly? (y/n): " result
        result=$(echo "$result" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
        if [ "$result" = "y" ] || [ "$result" = "yes" ]; then
            print_result "if_all_exist operator" "PASS"
        else
            print_result "if_all_exist operator" "FAIL"
        fi

        read -p "   Did if_any_exist work correctly? (y/n): " result
        result=$(echo "$result" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
        if [ "$result" = "y" ] || [ "$result" = "yes" ]; then
            print_result "if_any_exist operator" "PASS"
        else
            print_result "if_any_exist operator" "FAIL"
        fi

        read -p "   Did if_screen work correctly? (y/n): " result
        result=$(echo "$result" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
        if [ "$result" = "y" ] || [ "$result" = "yes" ]; then
            print_result "if_screen operator" "PASS"
        else
            print_result "if_screen operator" "FAIL"
        fi

        read -p "   Did nested conditionals work correctly? (y/n): " result
        result=$(echo "$result" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
        if [ "$result" = "y" ] || [ "$result" = "yes" ]; then
            print_result "Nested conditionals" "PASS"
        else
            print_result "Nested conditionals" "FAIL"
        fi
        ;;
esac
echo ""

# ============================================================
# Phase 4: Summary
# ============================================================

echo "─────────────────────────────────────────────────────────────"
echo "Test Summary"
echo "─────────────────────────────────────────────────────────────"
echo ""
echo "Total Tests:  $TOTAL_TESTS"
echo -e "Passed:       ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed:       ${RED}$FAILED_TESTS${NC}"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✓ All Integration Tests Passed!          ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ✗ Some Tests Failed - Review Above        ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════╝${NC}"
    exit 1
fi
