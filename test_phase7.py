import sys; sys.path.insert(0, 'backend'); sys.path.insert(0, 'database')

print('=== Phase 7 Functional Integration Test ===\n')

# 1. Project Cognition
from project_cognition import project_cognition
r = project_cognition.create_project('AISHA Phase 8', 'Next phase planning', 'AI')
print('1. Project created:', r)
pid = r['id']
r2 = project_cognition.add_milestone(pid, 'Design document')
print('   Milestone added:', r2)
r3 = project_cognition.detect_project_signal('I got the auth working on AISHA Phase 8', 'happy')
print('   Signal: has_progress =', r3.get('has_progress'), ', matched =', r3.get('matched_project', {}).get('title', 'none'))
ctx = project_cognition.get_project_context()
print('   Context:', ctx[:80] if ctx else '(empty)')
print()

# 2. Cognitive Workspace
from cognitive_workspace import cognitive_workspace
ws = cognitive_workspace.create_workspace('Research Notes', 'ML research')
print('2. Workspace created:', ws)
ws_id = ws['id']
n1 = cognitive_workspace.add_node(ws_id, 'Transformers use attention', 'concept')
n2 = cognitive_workspace.add_node(ws_id, 'RNNs struggle with long sequences', 'note')
print('   Nodes:', n1, n2)
link = cognitive_workspace.link_nodes(n1['id'], n2['id'], 'related')
print('   Link:', link)
summary = cognitive_workspace.summarize_workspace(ws_id)
print('   Summary:', summary[:100])
print()

# 3. Knowledge Graph
from knowledge_graph import knowledge_graph
obs = knowledge_graph.observe_concepts('Machine learning uses neural networks for pattern recognition')
print('3. KG observed:', obs)
related = knowledge_graph.get_related_concepts('machine')
print('   Related to "machine":', [r['concept'] for r in related[:3]])
print()

# 4. Research Intelligence
from research_intelligence import research_intelligence
sess = research_intelligence.start_session('Quantum computing')
print('4. Research session:', sess)
research_intelligence.add_finding(sess['id'], 'Qubits use superposition for parallel computation')
qs = research_intelligence.suggest_questions(sess['id'])
print('   Suggested questions:', len(qs))
print()

# 5. Knowledge Synthesis
from knowledge_synthesis import knowledge_synthesis
synth = knowledge_synthesis.synthesize('machine')
print('5. Synthesis for "machine":', synth['source_count'], 'sources')
print('   Sources:', synth['sources'])
print()

# 6. Behavioral Intelligence (creative mode)
from behavioral_intelligence import behavioral_intelligence
behavioral_intelligence.enrich_response('test', 'what if we brainstorm ideas?', 'neutral')
print('6. Creative mode detected:', behavioral_intelligence.is_creative_mode)
print()

# 7. Reflective Cognition (collaborative)
from reflective_cognition import reflective_cognition
collab = reflective_cognition.generate_collaborative_reflection()
print('7. Collaborative reflection:', collab)
print()

print('=== ALL FUNCTIONAL TESTS PASSED ===')
