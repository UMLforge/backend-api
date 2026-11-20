from fastapi import APIRouter, Depends, Request, Response

from ..db import DiagramRepo
from ..errors import AppError
from .admin import require_admin
from ..models import DiagramIn, DiagramMeta, DiagramOut

router = APIRouter(prefix="/api/diagrams", tags=["diagrams"])


def get_repo(request: Request) -> DiagramRepo:
    return request.app.state.repo


NOT_FOUND = AppError(404, "This diagram no longer exists", "Someone may have deleted it.",
                     "Press Save to keep your current drawing as a new diagram.")


def _found(item):
    if item is None:
        raise NOT_FOUND
    return item


@router.get("", response_model=list[DiagramMeta])
def list_diagrams(repo: DiagramRepo = Depends(get_repo), _admin: str = Depends(require_admin)):
    """Admins only: there are no user accounts, so a public list would show everyone's diagrams.
    People find their own diagrams through their browser's project library (frontend io/projects.js)."""
    return repo.list()


@router.get("/{diagram_id}", response_model=DiagramOut)
def get_diagram(diagram_id: str, repo: DiagramRepo = Depends(get_repo)):
    return _found(repo.get(diagram_id))


@router.post("", response_model=DiagramOut, status_code=201)
def create_diagram(body: DiagramIn, repo: DiagramRepo = Depends(get_repo)):
    return repo.create(body.title, body.diagram)


@router.put("/{diagram_id}", response_model=DiagramOut)
def update_diagram(diagram_id: str, body: DiagramIn, repo: DiagramRepo = Depends(get_repo)):
    return _found(repo.update(diagram_id, body.title, body.diagram))


@router.delete("/{diagram_id}", status_code=204)
def delete_diagram(diagram_id: str, repo: DiagramRepo = Depends(get_repo)):
    if not repo.delete(diagram_id):
        raise NOT_FOUND
    return Response(status_code=204)
