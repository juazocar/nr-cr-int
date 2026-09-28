from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field
ClientName=Literal["WATCH","DESKTOP","CORE","MOBILE","AGENT"]
class ActionCreate(BaseModel):
    source: ClientName
    target: ClientName
    action_type: str=Field(...,min_length=1,max_length=80)
    description: str=Field(...,min_length=1,max_length=1000)
    payload: dict[str,Any]=Field(default_factory=dict)
    requires_confirmation: bool=True
class ActionTransition(BaseModel):
    actor: ClientName
    error: str|None=Field(default=None,max_length=2000)
    result: dict[str,Any]|None=None
