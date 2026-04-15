"""
Agent services for forked agent support.

Provides:
- transcript.py: Agent transcript recording
- tracing.py: Perfetto tracing
- hooks.py: Frontmatter hooks
- skill_preload.py: Skill preloading
- remote_backend.py: Remote/tmux backend
"""
from py_claw.services.agent.hooks import (
    AgentHook,
    AgentHooksService,
    clear_agent_hooks,
    register_agent_hooks,
)
from py_claw.services.agent.remote_backend import (
    RemoteAgentBackend,
    RemoteBackendConfig,
    SSHAgentBackend,
    TmuxAgentBackend,
    create_remote_backend,
)
from py_claw.services.agent.skill_preload import (
    PreloadedSkill,
    SkillPreloadResult,
    SkillPreloadService,
    preload_agent_skills,
    resolve_skill_name,
)
from py_claw.services.agent.tracing import (
    PerfettoTracingService,
    TraceSpan,
)
from py_claw.services.agent.transcript import (
    AgentMetadata,
    AgentTranscriptService,
    clear_agent_transcript_subdir,
    read_agent_metadata,
    read_agent_transcript,
    record_sidechain_transcript,
    set_agent_transcript_subdir,
    write_agent_metadata,
)


__all__ = [
    # transcript
    "AgentMetadata",
    "AgentTranscriptService",
    "clear_agent_transcript_subdir",
    "read_agent_metadata",
    "read_agent_transcript",
    "record_sidechain_transcript",
    "set_agent_transcript_subdir",
    "write_agent_metadata",
    # tracing
    "PerfettoTracingService",
    "TraceSpan",
    # hooks
    "AgentHook",
    "AgentHooksService",
    "clear_agent_hooks",
    "register_agent_hooks",
    # skill_preload
    "PreloadedSkill",
    "SkillPreloadResult",
    "SkillPreloadService",
    "preload_agent_skills",
    "resolve_skill_name",
    # remote_backend
    "RemoteAgentBackend",
    "RemoteBackendConfig",
    "SSHAgentBackend",
    "TmuxAgentBackend",
    "create_remote_backend",
]
