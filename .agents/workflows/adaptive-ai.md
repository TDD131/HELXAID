<SYSTEM_DIRECTIVE>
This workflow enforces strict adaptive reasoning depth based on explicit user modifiers.
You MUST process these rules before executing any task.
</SYSTEM_DIRECTIVE>

<RULES>
  <RULE id="1" name="Mandatory Depth Modifier">
    <CONDITION>User request involves substantive logic, architecture, or code changes.</CONDITION>
    <ACTION>Verify presence of depth modifier: `/deep-low`, `/deep-medium`, `/deep-high`, or `/deep-high-extreme`.</ACTION>
    <IF_MISSING>Halt execution. Politely ask the user to provide a depth modifier.</IF_MISSING>
  </RULE>

  <RULE id="2" name="Dynamic Leveling (Sequential Synergy)">
    <CONDITION>User provides `/squential-thinking` AND a `/deep-*` modifier.</CONDITION>
    <ACTION>Calculate effective reasoning depth using the following matrix:</ACTION>
    <MATRIX>
      <CASE match="/deep-low">
        <SET_LEVEL>1.5</SET_LEVEL>
        <BEHAVIOR>Execute: Exhaustive research + Context mapping + Sequential thought trace for edge cases.</BEHAVIOR>
      </CASE>
      <CASE match="/deep-medium">
        <SET_LEVEL>2.5</SET_LEVEL>
        <BEHAVIOR>Execute: Execution flow trace + State machine audit + Sequential validation of alternatives & performance.</BEHAVIOR>
      </CASE>
      <CASE match="/deep-high">
        <SET_LEVEL>3.5</SET_LEVEL>
        <BEHAVIOR>Execute: Global impact analysis + Stress testing + Sequential mapping of multi-stage failures.</BEHAVIOR>
      </CASE>
      <CASE match="/deep-high-extreme">
        <SET_LEVEL>4.5 (MAXIMUM)</SET_LEVEL>
        <BEHAVIOR>Execute: Complete system audit + Sequential analysis of every dependency and multi-vector failure simulation.</BEHAVIOR>
      </CASE>
    </MATRIX>
  </RULE>

  <RULE id="3" name="Execution Protocol">
    <ACTION_1>Align architectural decisions, actions, and output style perfectly with user instructions.</ACTION_1>
    <ACTION_2>Output a confirmation message BEFORE starting execution stating the calculated level (e.g., "Applying Level 2.5 Analysis: /deep-medium + /squential-thinking").</ACTION_2>
  </RULE>
</RULES>
