#!/usr/bin/env python3
"""
Универсальная логика проверки обновлений через GitHub Releases API.

Используется GUI и потенциально CLI: загрузка релизов, фильтрация по каналу
(stable / devel), сравнение версий через packaging (semver).

Каналы:
- stable: только обычные релизы (prerelease=False), без тегов/имен с DEVEL.
- devel: только pre-release с маркером DEVEL в tag_name или name.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

import requests
from packaging import version as pkg_version

logger = logging.getLogger(__name__)

DEFAULT_REPO = "rosakodu/zapretdeck"
GITHUB_RELEASES_URL = "https://api.github.com/repos/{repo}/releases"
GITHUB_API_VERSION = "2022-11-28"

Channel = Literal["stable", "devel"]


@dataclass(frozen=True)
class GitHubReleaseInfo:
    """Данные релиза, достаточные для скачивания zipball и отображения."""

    tag_name: str
    semver_text: str
    zipball_url: str
    html_url: str
    prerelease: bool
    name: str


def normalize_version_for_semver(raw: str) -> str:
    """
    Приводит строку версии из тега или из main.py к виду, который понимает packaging.

    Убирает префиксы ZapretDeck_, v / v., суффикс DEVEL и лишние пробелы.
    """
    s = raw.strip()
    s = re.sub(r"(?i)^zapretdeck[_\s-]+", "", s)
    s = re.sub(r"(?i)\s+devel\s*$", "", s)
    s = re.sub(r"(?i)^v\.?", "", s.strip())
    return s.strip()


def parse_local_version(raw: str) -> pkg_version.Version:
    """Парсит локальную версию приложения (например \"0.2.2\" или \"0.2.2 DEVEL\")."""
    return pkg_version.parse(normalize_version_for_semver(raw))


def _release_has_devel_marker(rel: Dict[str, Any]) -> bool:
    tag = (rel.get("tag_name") or "").upper()
    name = (rel.get("name") or "").upper()
    return "DEVEL" in tag or "DEVEL" in name


def release_matches_channel(rel: Dict[str, Any], channel: Channel) -> bool:
    """Определяет, относится ли релиз к выбранному каналу обновлений."""
    if rel.get("draft"):
        return False
    prerelease = bool(rel.get("prerelease", False))
    has_devel = _release_has_devel_marker(rel)

    if channel == "stable":
        if prerelease:
            return False
        if has_devel:
            return False
        return True

    # devel: только pre-release с явным маркером DEVEL
    if not prerelease:
        return False
    if not has_devel:
        return False
    return True


def _release_to_info(rel: Dict[str, Any]) -> Optional[GitHubReleaseInfo]:
    tag = (rel.get("tag_name") or "").strip()
    if not tag:
        return None
    zipball = rel.get("zipball_url")
    if not zipball:
        logger.warning("Релиз %s: нет zipball_url", tag)
        return None
    sem = normalize_version_for_semver(tag)
    try:
        pkg_version.parse(sem)
    except Exception as e:
        logger.warning("Не удалось разобрать semver из тега %r: %s", tag, e)
        return None
    return GitHubReleaseInfo(
        tag_name=tag,
        semver_text=sem,
        zipball_url=zipball,
        html_url=(rel.get("html_url") or ""),
        prerelease=bool(rel.get("prerelease")),
        name=(rel.get("name") or ""),
    )


def fetch_all_releases(
    repo: str = DEFAULT_REPO,
    timeout: float = 15.0,
    session: Optional[requests.Session] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Загружает все опубликованные релизы (с пагинацией).

    Returns:
        (список объектов релиза, сообщение об ошибке или None при успехе)
    """
    sess = session or requests.Session()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "ZapretDeck-UpdateChecker",
    }
    url = GITHUB_RELEASES_URL.format(repo=repo)
    out: List[Dict[str, Any]] = []
    page = 1
    per_page = 100

    while True:
        try:
            r = sess.get(
                url,
                params={"per_page": per_page, "page": page},
                headers=headers,
                timeout=timeout,
            )
        except requests.exceptions.RequestException as e:
            logger.error("Сеть/GitHub: запрос релизов не удался: %s", e)
            return [], str(e)

        if r.status_code == 403:
            msg = ""
            try:
                msg = (r.json() or {}).get("message", "")
            except Exception:
                pass
            remaining = r.headers.get("X-RateLimit-Remaining", "?")
            logger.error(
                "GitHub API 403 (лимит или запрет). remaining=%s message=%s",
                remaining,
                msg,
            )
            return [], f"GitHub API: 403 {msg or 'forbidden'}"

        if r.status_code == 404:
            logger.error("Репозиторий не найден: %s", repo)
            return [], "Repository not found"

        if r.status_code != 200:
            snippet = (r.text or "")[:400]
            logger.error("GitHub API: HTTP %s — %s", r.status_code, snippet)
            return [], f"GitHub API error: HTTP {r.status_code}"

        try:
            batch = r.json()
        except ValueError as e:
            logger.error("Ответ GitHub не JSON: %s", e)
            return [], "Invalid JSON from GitHub"

        if not isinstance(batch, list):
            return [], "Unexpected GitHub response"

        if not batch:
            break
        out.extend(batch)
        if len(batch) < per_page:
            break
        page += 1

    logger.debug("Загружено релизов с GitHub: %d", len(out))
    return out, None


def find_newer_release(
    current_version: str,
    channel: Channel,
    releases: List[Dict[str, Any]],
) -> Optional[GitHubReleaseInfo]:
    """
    Выбирает самый новый релиз канала, semver которого строго больше локальной версии.
    """
    try:
        local_v = parse_local_version(current_version)
    except Exception as e:
        logger.error("Локальная версия не разобрана %r: %s", current_version, e)
        return None

    candidates: List[GitHubReleaseInfo] = []
    for rel in releases:
        if not release_matches_channel(rel, channel):
            continue
        info = _release_to_info(rel)
        if info is None:
            continue
        try:
            remote_v = pkg_version.parse(info.semver_text)
        except Exception:
            continue
        if remote_v > local_v:
            candidates.append(info)

    if not candidates:
        logger.info(
            "Обновления (%s): актуальная версия (локально=%s → %s)",
            channel,
            current_version,
            normalize_version_for_semver(current_version),
        )
        return None

    best = max(candidates, key=lambda c: pkg_version.parse(c.semver_text))
    logger.info(
        "Обновления (%s): доступно новее — tag=%s semver=%s (было %s)",
        channel,
        best.tag_name,
        best.semver_text,
        normalize_version_for_semver(current_version),
    )
    return best


def check_for_updates_sync(
    current_version: str,
    channel: Channel,
    repo: str = DEFAULT_REPO,
    timeout: float = 15.0,
    session: Optional[requests.Session] = None,
) -> Tuple[Optional[GitHubReleaseInfo], Optional[str]]:
    """
    Синхронная проверка: загрузка релизов и поиск более нового для канала.

    Returns:
        (информация о релизе или None, текст ошибки или None)

    Пример:
        info, err = check_for_updates_sync(\"0.2.2\", \"stable\")
        if err:
            print(err)
        elif info:
            print(info.tag_name, info.zipball_url)
    """
    releases, err = fetch_all_releases(repo=repo, timeout=timeout, session=session)
    if err:
        return None, err
    found = find_newer_release(current_version, channel, releases)
    return found, None
