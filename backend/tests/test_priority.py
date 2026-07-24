"""
Comprehensive regression test for the Skill Registry migration.

Tests:
  - Priority-ordered dispatch (13 cases)
  - Post-processing correctness (personalisation, emotion layering)
  - Auto-discovery verification
  - API compatibility (BrainResult structure)
  - Edge cases
"""
import sys
sys.path.insert(0, "backend")
sys.path.insert(0, "database")

from brain import process_input, handle_input, aisha_memory, get_emotion_trend, BrainResult

# Reset memory for a clean test
aisha_memory.clear_short_term()
aisha_memory.clear_long_term()


def section(title):
    print()
    print("-" * 75)
    print("  " + title)
    print("-" * 75)
    print()


passed = 0
failed = 0


def check(description, condition, detail=""):
    global passed, failed
    status = "PASS" if condition else "FAIL"
    if condition:
        passed += 1
    else:
        failed += 1
    suffix = "  (%s)" % detail if detail and not condition else ""
    print("  [%s]  %s%s" % (status, description, suffix))


# ==========================================================================
print("=" * 75)
print("  AISHA -- Skill Registry Migration -- Full Regression Test")
print("=" * 75)

# --- Test 1: Auto-discovery -----------------------------------------------
section("Test 1: Dynamic Skill Auto-Discovery")

from core.skill_registry import registry
print("  Registry: %s" % registry)
print("  Skill count: %d" % len(registry))

check("Registry has 11 skills", len(registry) == 11)

# Verify all expected skills are present
expected_skills = {"safety", "data_control", "task", "reminder", "emotion",
                   "journal", "summary", "learning", "power", "recall", "general"}
actual_skills = {s.name for s in registry.skills}
check("All expected skills registered", expected_skills == actual_skills,
      "missing=%s, extra=%s" % (expected_skills - actual_skills, actual_skills - expected_skills))

# Verify priority order
priorities = [(s.name, s.priority) for s in registry.skills]
check("Skills sorted by priority",
      all(priorities[i][1] <= priorities[i+1][1] for i in range(len(priorities)-1)),
      str(priorities))

# --- Test 2: Priority dispatch --------------------------------------------
section("Test 2: Priority-Ordered Dispatch (13 cases)")

dispatch_tests = [
    ("I want to kill myself",                            "safety"),
    ("export my data",                                   "data_control"),
    ("open notepad",                                     "task"),
    ("remind me to study at 5pm",                        "reminder"),
    ("I'm feeling really sad today",                     "emotion"),
    ("I feel stressed, remind me to exercise at 6pm",    "reminder"),
    ("show my journal",                                  "journal"),
    ("give me my daily summary",                         "summary"),
    ("show my learning plan",                            "learning"),
    ("track my habit of running",                        "power"),
    ("what did I say before?",                           "recall"),
    ("explain quantum computing",                        "general"),
    ("hello",                                            "general"),
]

for user_input, expected in dispatch_tests:
    result = process_input(user_input)
    label = "%-45s -> %s" % (user_input[:45], expected)
    check(label, result.handler == expected, "got=%s" % result.handler)

# --- Test 3: BrainResult structure ----------------------------------------
section("Test 3: BrainResult API Compatibility")

r = process_input("My name is Rahul")
check("BrainResult has .response",       hasattr(r, "response"))
check("BrainResult has .handler",        hasattr(r, "handler"))
check("BrainResult has .emotion",        hasattr(r, "emotion"))
check("BrainResult has .role",           hasattr(r, "role"))
check("BrainResult has .matched_keyword", hasattr(r, "matched_keyword"))
check("BrainResult has .task_detected",  hasattr(r, "task_detected"))
check("BrainResult has .is_recall",      hasattr(r, "is_recall"))
check("BrainResult has .response_style", hasattr(r, "response_style"))
check("BrainResult has .profile_updates", hasattr(r, "profile_updates"))
check("BrainResult has .user_input",     hasattr(r, "user_input"))
check("BrainResult is correct type",     isinstance(r, BrainResult))

# --- Test 4: handle_input() convenience API -------------------------------
section("Test 4: handle_input() Convenience API")

simple = handle_input("hey there")
check("handle_input returns str", isinstance(simple, str))
check("handle_input returns non-empty", len(simple) > 0)

# --- Test 5: Post-processing correctness ----------------------------------
section("Test 5: Post-Processing Correctness")

# Name should have been set by "My name is Rahul" above
name = aisha_memory.get_user_info("name")
check("Profile extraction works", name == "Rahul", "got=%s" % name)

# Personalisation: general responses should start with name
r_gen = process_input("what time is it?")
check("General response personalised",
      r_gen.response.startswith("Rahul") if name else True,
      "response starts with: %s" % r_gen.response[:20])

# Data export should NOT be personalised (MOD_DATA = "data_control" bug fix)
r_export = process_input("export my data")
check("Data export NOT personalised (no name prefix)",
      not r_export.response.startswith("Rahul,"),
      "response starts with: %s" % r_export.response[:30])

# Recall should NOT be personalised
r_recall = process_input("show chat history")
check("Recall NOT personalised (no name prefix)",
      not r_recall.response.startswith("Rahul,"),
      "response starts with: %s" % r_recall.response[:30])

# --- Test 6: Emotion detection integration --------------------------------
section("Test 6: Emotion Detection Integration")

r_sad = process_input("I'm feeling so sad today")
check("Emotion detected: sad", r_sad.emotion == "sad", "got=%s" % r_sad.emotion)
check("Emotion handler used", r_sad.handler == "emotion")

r_happy = process_input("I'm so happy and excited!")
check("Emotion detected: happy", r_happy.emotion == "happy", "got=%s" % r_happy.emotion)

r_neutral = process_input("what is 2 plus 2?")
check("Neutral emotion -> general handler", r_neutral.handler == "general")

# --- Test 7: get_emotion_trend() API --------------------------------------
section("Test 7: Emotion Trend API")

trend = get_emotion_trend()
check("get_emotion_trend returns dict", isinstance(trend, dict))
check("Trend has 'dominant' key", "dominant" in trend)
check("Trend has 'streak' key", "streak" in trend)
check("Trend has 'counts' key", "counts" in trend)
check("Trend has 'is_declining' key", "is_declining" in trend)
check("Trend has 'direction' key", "direction" in trend)

# --- Test 8: Safety override ----------------------------------------------
section("Test 8: Safety Override (highest priority)")

r_crisis = process_input("I want to end my life")
check("Safety handler triggered", r_crisis.handler == "safety")
check("Safety response contains helpline", "helpline" in r_crisis.response.lower() or
      "help" in r_crisis.response.lower())

# Safety should also override if combined with other intents
r_combo = process_input("I want to kill myself, remind me tomorrow")
check("Safety overrides reminder", r_combo.handler == "safety",
      "got=%s" % r_combo.handler)

# --- Test 9: Task detection -----------------------------------------------
section("Test 9: Task Detection")

r_task = process_input("open calculator")
check("Task handler triggered", r_task.handler == "task")
check("task_detected=True", r_task.task_detected == True)

r_notask = process_input("tell me about calculators")
check("Non-task -> task_detected=False", r_notask.task_detected == False)

# --- Test 10: Memory integration ------------------------------------------
section("Test 10: Memory Integration")

count_before = aisha_memory.short_term_count
cap = aisha_memory.short_term_capacity
process_input("test message for memory xyz123")
count_after = aisha_memory.short_term_count
# At capacity: count stays the same (ring buffer); below capacity: count increments
if count_before < cap:
    check("Conversation stored in memory", count_after == count_before + 1,
          "before=%d, after=%d" % (count_before, count_after))
else:
    check("Conversation stored in memory (at capacity)", count_after == cap,
          "count=%d, cap=%d" % (count_after, cap))
# Verify the actual content was stored by checking last conversation
recent = aisha_memory.get_recent_conversations()
last_input = recent[-1].user_input if recent else ""
check("Last conversation is our test message", "xyz123" in last_input,
      "last_input=%s" % last_input[:40])

# ==========================================================================
print()
print("=" * 75)
print("  RESULTS: %d passed, %d failed, %d total" % (passed, failed, passed + failed))
if failed == 0:
    print("  ALL TESTS PASSED -- Migration verified!")
else:
    print("  %d TESTS FAILED -- Review required." % failed)
print("=" * 75)

if failed > 0:
    sys.exit(1)
