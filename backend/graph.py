# graph.py
from langgraph.graph import StateGraph, END

from backend.nodes import (
    analyze_jd,
    resume_analyzer,
    resume_writer,
    rewritten_resume_analyzer,
    tex_file_creator,
    compile_pdf,
    should_continue,
    should_continue_after_rewrite,
    should_retry,
)
from backend.models import Match_Analysis


def build_graph():
    workflow = StateGraph(Match_Analysis)

    workflow.add_node("analyze_jd", analyze_jd)
    workflow.add_node("resume_analyzer", resume_analyzer)
    workflow.add_node("resume_writer", resume_writer)
    workflow.add_node("rewritten_resume_analyzer", rewritten_resume_analyzer)
    workflow.add_node("tex_file_creator", tex_file_creator)
    workflow.add_node("compile_pdf", compile_pdf)

    workflow.set_entry_point("analyze_jd")
    workflow.add_edge("analyze_jd", "resume_analyzer")
    workflow.add_conditional_edges(
        "resume_analyzer",
        should_continue,
        {"continue": "resume_writer", "stop": END},
    )
    workflow.add_edge("resume_writer", "rewritten_resume_analyzer")
    workflow.add_conditional_edges(
        "rewritten_resume_analyzer",
        should_continue_after_rewrite,
        {"continue": "tex_file_creator", "retry": "resume_writer"},
    )
    workflow.add_edge("tex_file_creator", "compile_pdf")
    workflow.add_conditional_edges(
        "compile_pdf",
        should_retry,
        {"success": END, "retry": "resume_writer", "give_up": END},
    )

    return workflow.compile()


app = build_graph()
