import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import BackgroundTasks
from app.src.services.base_service import base_service
from app.src.services.import_document import import_document


router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")
UPLOAD_DIR = Path("app/data/imports")
ALLOWED_EXTENSIONS = {".csv", ".pdf"}


def is_authenticated(request: Request) -> bool:
    return request.cookies.get("admin_session") == "authenticated"


def redirect_to_admin(message: str | None = None, error: str | None = None) -> RedirectResponse:
    url = "/admin"
    params = []
    if message:
        params.append(f"message={message}")
    if error:
        params.append(f"error={error}")
    if params:
        url = f"{url}?{'&'.join(params)}"
    return RedirectResponse(url=url, status_code=303)


@router.get("")
async def admin_page(request: Request):
    if not is_authenticated(request):
        return templates.TemplateResponse(
            "admin_login.html",
            {
                "request": request,
                "error": request.query_params.get("error"),
            },
        )

    stats = import_document.get_document_stats()
    documents = import_document.list_documents()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "stats": stats,
            "documents": documents,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/login")
async def admin_login(username: str = Form(...), password: str = Form(...)):
    if username != base_service.admin_username or password != base_service.admin_password:
        return RedirectResponse(url="/admin?error=login_failed", status_code=303)

    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie(
        key="admin_session",
        value="authenticated",
        httponly=True,
        max_age=60 * 60 * 8,
        samesite="lax",
    )
    return response


@router.post("/logout")
async def admin_logout():
    response = RedirectResponse(url="/admin", status_code=303)
    response.delete_cookie("admin_session")
    return response


@router.post("/documents")
async def upload_document(request: Request, file: UploadFile = File(...)):
    if not is_authenticated(request):
        return RedirectResponse(url="/admin", status_code=303)

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return redirect_to_admin(error="invalid_file_type")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    target_path = UPLOAD_DIR / safe_name

    try:
        with target_path.open("wb") as output:
            shutil.copyfileobj(file.file, output)
        stats = import_document.import_db(
            target_path,
            original_filename=file.filename,
        )
    except Exception as exc:
        if target_path.exists():
            target_path.unlink()
        print(f"[ADMIN_IMPORT_ERROR] {exc}")
        return redirect_to_admin(error="import_failed")
    finally:
        await file.close()

    message = (
        f"imported_{stats['documents']}_docs_"
        f"{stats['chunks']}_chunks_"
        f"{stats['entities']}_entities_"
        f"{stats['relationships']}_relationships"
    )
    return redirect_to_admin(message=message)

@router.get("/update-comunities")
async def update_community(
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(
        import_document.update_communities
    )

    return {
        "success": True,
        "message": "Community update started",
    }

@router.get("/update-comunities-big-context")
async def update_community_bigcontext(
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(
        import_document.update_communities_big_context
    )

    return {
        "success": True,
        "message": "Community update started",
    }


@router.get("/update-extract-entities-relationship-big-context")
async def update_extract_entities_relationship_big_context(
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(
        import_document.update_entity
    )

    return {
        "success": True,
        "message": "Community update started",
    }


@router.post("/documents/delete")
async def delete_document(request: Request, file_name: str = Form(...)):
    if not is_authenticated(request):
        return RedirectResponse(url="/admin", status_code=303)
    try:
        deleted = import_document.delete_document(file_name)
    except Exception as exc:
        print(f"[ADMIN_DELETE_ERROR] {exc}")
        return redirect_to_admin(error="delete_failed")

    return redirect_to_admin(message=f"deleted_{deleted['documents']}_docs")
