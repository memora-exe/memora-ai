"""Parsed document storage client.

Parsed markdown and metadata live in the backend object store. This module keeps
search semantics in AI while all persistence crosses the authenticated internal API.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings
from app.services.document_processor import clean_extracted_text


def _project_dir(project_id: str) -> Path:
    """Compatibility validation; AI never creates a local storage directory."""
    if (
        not project_id
        or '/' in project_id
        or '\\' in project_id
        or Path(project_id).name != project_id
        or project_id in {'.', '..'}
    ):
        raise ValueError(f"Invalid project id: {project_id}")
    return Path(settings.STORAGE_BASE_DIR).resolve() / 'projects' / project_id


def _safe_resolve(project_id: str, filename: str) -> Path:
    """Validate names for callers; parsed data is not stored on this filesystem."""
    base = _project_dir(project_id).resolve()
    if not filename or not isinstance(filename, str):
        raise ValueError(f"Path traversal blocked: {filename}")
    if (
        filename in {'.', '..'}
        or filename.startswith(('.', '/', '\\'))
        or filename.startswith('//')
        or filename.startswith('\\\\')
    ):
        raise ValueError(f"Path traversal blocked: {filename}")
    path_obj = Path(filename)
    if path_obj.is_absolute() or path_obj.drive or path_obj.root or path_obj.anchor:
        raise ValueError(f"Path traversal blocked: {filename}")
    parts = path_obj.parts
    if '..' in parts or '.' in parts or any(p.startswith('.') for p in parts):
        raise ValueError(f"Path traversal blocked: {filename}")
    if '/' in filename or '\\' in filename:
        raise ValueError(f"Path traversal blocked: {filename}")
    target = (base / path_obj.name).resolve()
    if not target.is_relative_to(base):
        raise ValueError(f"Path traversal blocked: {filename}")
    return target


def _headers() -> dict[str, str]:
    if not settings.MEMORA_INTERNAL_TOKEN:
        raise RuntimeError('MEMORA_INTERNAL_TOKEN is not configured')
    return {'X-Internal-Token': settings.MEMORA_INTERNAL_TOKEN}


def _request(method: str, path: str, **kwargs):
    url = f"{settings.NESTJS_API_URL.rstrip('/')}{path}"
    with httpx.Client(timeout=kwargs.pop('timeout', 60.0)) as client:
        response = client.request(method, url, headers=_headers(), **kwargs)
    if response.status_code == 404:
        return {'_status': 404, 'error': 'Not found'}
    if response.status_code >= 400:
        raise RuntimeError(f"Storage API {method} {path} returned {response.status_code}: {response.text[:300]}")
    return response.json() if response.content else {}


def _clean_id(file_id: str) -> str:
    return file_id[:-3] if file_id.endswith('.md') else file_id


def save_document(project_id: str, file_id: str, markdown_content: str, metadata: Optional[dict] = None) -> None:
    clean_id = _clean_id(file_id)
    _safe_resolve(project_id, f'{clean_id}.md')
    cleaned_content = clean_extracted_text(markdown_content)
    _request('POST', f'/internal/files/{clean_id}/parsed', json={
        'projectId': project_id,
        'content': cleaned_content,
        'metadata': metadata or {},
    })


def read_document(project_id: str, file_id: str, offset: int = 1, limit: int = 100) -> dict:
    if offset < 1 or limit < 1:
        raise ValueError('offset must be >= 1 and limit must be >= 1')
    clean_id = _clean_id(file_id)
    _safe_resolve(project_id, f'{clean_id}.md')
    try:
        data = _request('GET', f'/internal/files/{clean_id}/parsed', params={'projectId': project_id})
    except Exception:
        return {'error': f'File {file_id} not found'}
    if not data or data.get('_status') == 404 or 'error' in data:
        return {'error': f'File {file_id} not found'}
    raw_content = str(data.get('content', ''))
    cleaned = clean_extracted_text(raw_content)
    lines = cleaned.splitlines()
    metadata = data.get('metadata') or {}
    return {
        'file_id': _clean_id(file_id),
        'original_name': metadata.get('originalName', f'{_clean_id(file_id)}.md'),
        'total_lines': len(lines),
        'offset': offset,
        'limit': limit,
        'content': '\n'.join(lines[offset - 1:offset - 1 + limit]),
    }


def read_full_text(project_id: str, file_id: str) -> str:
    clean_id = _clean_id(file_id)
    _safe_resolve(project_id, f'{clean_id}.md')
    try:
        data = _request('GET', f'/internal/files/{clean_id}/parsed', params={'projectId': project_id})
    except Exception:
        return ''
    if not data or data.get('_status') == 404 or 'error' in data:
        return ''
    return clean_extracted_text(str(data.get('content', '')))


def list_documents(project_id: str, pattern: str = '*') -> list[dict]:
    _project_dir(project_id)
    if Path(pattern).is_absolute() or '..' in Path(pattern).parts or pattern.startswith(('/', '\\')):
        raise ValueError(f'Path traversal blocked: {pattern}')
    try:
        results = _request('GET', f'/internal/files/project/{project_id}/parsed')
    except Exception:
        return []
    clean_pattern = pattern if pattern.endswith('.md') else f"{pattern}.md"
    regex = re.compile('^' + re.escape(clean_pattern).replace(r'\*', '.*').replace(r'\?', '.') + '$')
    return [item for item in results if regex.match(f"{item.get('file_id', '')}.md")]


def _parse_rg_output(project_id: str, stdout: str, max_results: int) -> list[dict]:
    records = []
    for raw_line in stdout.splitlines():
        if raw_line == '--':
            continue
        match_line = re.match(r'^(.*?):(\d+):(.*)$', raw_line)
        is_match = match_line is not None
        if match_line is None:
            match_line = re.match(r'^(.*?)-(\d+)-(.*)$', raw_line)
        if match_line is None:
            continue
        path_text, line_text, text = match_line.groups()
        records.append((Path(path_text), int(line_text), text, is_match))

    results = []
    for path, line_number, _, is_match in records:
        if not is_match:
            continue
        context = [
            f'{record_line}: {record_text}'
            for record_path, record_line, record_text, _ in records
            if record_path == path and abs(record_line - line_number) <= 2
        ]
        results.append({
            'file_id': path.stem,
            'original_name': f'{path.stem}.md',
            'line_number': line_number,
            'snippet': '\n'.join(context),
        })
        if len(results) >= max_results:
            break
    return results


def grep_documents(project_id: str, query: str, path_pattern: str = '*.md', case_sensitive: bool = False, max_results: int = 50) -> list[dict]:
    if not query or max_results <= 0:
        return []
    files = list_documents(project_id, path_pattern)
    flags = 0 if case_sensitive else re.IGNORECASE
    matcher = re.compile(re.escape(query), flags)
    results: list[dict] = []
    for file in files:
        text = read_full_text(project_id, file['file_id'])
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if matcher.search(line):
                start, end = max(0, index - 2), min(len(lines), index + 3)
                results.append({
                    'file_id': file['file_id'],
                    'original_name': file.get('original_name', f"{file['file_id']}.md"),
                    'line_number': index + 1,
                    'snippet': '\n'.join(f'{i + 1}: {lines[i]}' for i in range(start, end)),
                })
                if len(results) >= max_results:
                    return results
    return results


def delete_project_file(project_id: str, file_id: str) -> bool:
    clean_id = _clean_id(file_id)
    _safe_resolve(project_id, f'{clean_id}.md')
    try:
        _request('DELETE', f'/internal/files/{clean_id}/parsed', params={'projectId': project_id})
    except Exception:
        pass
    return True

