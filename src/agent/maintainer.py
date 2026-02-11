"""
專案管家 Agent (Maintainer) - 自動維護 README.md 儀表板

功能:
    - 掃描 site/content/posts/ 取得文章列表
    - 更新 README.md 的「最新快訊」表格 (最新 5 篇)
    - 更新文章數 Badge
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ArticleInfo:
    """文章資訊"""
    title: str
    date: str
    description: str = ""
    filename: str = ""
    url: str = ""

    def to_table_row(self) -> str:
        """轉換為 Markdown 表格行"""
        # 文章連結指向 Hugo 網站
        link = f"[{self.title}](site/content/posts/{self.filename})"
        return f"| {self.date} | {link} | {self.description[:50]}{'...' if len(self.description) > 50 else ''} |"


@dataclass
class MaintainerResult:
    """維護結果"""
    success: bool
    articles_found: int = 0
    readme_updated: bool = False
    error_message: Optional[str] = None
    changes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "articles_found": self.articles_found,
            "readme_updated": self.readme_updated,
            "error_message": self.error_message,
            "changes": self.changes,
        }


class MaintainerAgent:
    """
    專案管家 Agent - 維護 README.md 儀表板
    
    功能:
        - 掃描文章目錄
        - 更新最新快訊表格 (最新 5 篇)
        - 更新文章數 Badge
    
    使用方式:
        maintainer = MaintainerAgent()
        result = await maintainer.update_readme()
    """

    def __init__(
        self,
        working_dir: Optional[Path] = None,
        posts_dir: Optional[Path] = None,
        readme_path: Optional[Path] = None,
        max_articles: int = 5,
    ):
        """
        初始化專案管家
        
        Args:
            working_dir: 工作目錄
            posts_dir: 文章目錄
            readme_path: README 路徑
            max_articles: 顯示的最大文章數
        """
        self.working_dir = working_dir or Path.cwd()
        self.posts_dir = posts_dir or self.working_dir / "site" / "content" / "posts"
        self.readme_path = readme_path or self.working_dir / "README.md"
        self.max_articles = max_articles
        self.log = logger.bind(component="MaintainerAgent")

    async def update_readme(self) -> MaintainerResult:
        """
        更新 README.md 儀表板
        
        Returns:
            MaintainerResult: 維護結果
        """
        self.log.info("開始更新 README.md 儀表板")
        changes = []

        try:
            # Step 1: 掃描文章
            articles = self._scan_articles()
            self.log.info(f"找到 {len(articles)} 篇文章")

            if not articles:
                return MaintainerResult(
                    success=True,
                    articles_found=0,
                    readme_updated=False,
                    changes=["沒有找到任何文章"],
                )

            # Step 2: 讀取現有 README
            if not self.readme_path.exists():
                return MaintainerResult(
                    success=False,
                    error_message=f"README 不存在: {self.readme_path}",
                )

            readme_content = self.readme_path.read_text(encoding="utf-8")

            # Step 3: 更新最新快訊表格
            new_content, table_updated = self._update_news_table(
                readme_content, articles
            )
            if table_updated:
                changes.append("更新最新快訊表格")

            # Step 4: 更新文章數 Badge
            new_content, badge_updated = self._update_article_badge(
                new_content, len(articles)
            )
            if badge_updated:
                changes.append(f"更新文章數 Badge ({len(articles)} 篇)")

            # Step 5: 如果有變更，寫入檔案
            if new_content != readme_content:
                self.readme_path.write_text(new_content, encoding="utf-8")
                self.log.info("README.md 已更新", changes=changes)

                return MaintainerResult(
                    success=True,
                    articles_found=len(articles),
                    readme_updated=True,
                    changes=changes,
                )
            else:
                self.log.info("README.md 無需更新")
                return MaintainerResult(
                    success=True,
                    articles_found=len(articles),
                    readme_updated=False,
                    changes=["內容無變更"],
                )

        except Exception as e:
            self.log.error("README 更新失敗", error=str(e))
            return MaintainerResult(
                success=False,
                error_message=str(e),
            )

    def _scan_articles(self) -> list[ArticleInfo]:
        """掃描文章目錄"""
        articles = []

        if not self.posts_dir.exists():
            self.log.warning(f"文章目錄不存在: {self.posts_dir}")
            return articles

        for file_path in self.posts_dir.glob("*.md"):
            # 跳過 welcome.md 等非日期檔案
            if not re.match(r"\d{4}-\d{2}-\d{2}\.md", file_path.name):
                continue

            article = self._parse_article(file_path)
            if article:
                articles.append(article)

        # 按日期排序 (最新的在前)
        articles.sort(key=lambda a: a.date, reverse=True)

        return articles

    def _parse_article(self, file_path: Path) -> Optional[ArticleInfo]:
        """解析文章 Front Matter"""
        try:
            content = file_path.read_text(encoding="utf-8")

            # 解析 Front Matter
            if not content.startswith("---"):
                return None

            parts = content.split("---", 2)
            if len(parts) < 3:
                return None

            front_matter = parts[1]

            # 提取欄位
            title = self._extract_field(front_matter, "title")
            date = self._extract_field(front_matter, "date")
            description = self._extract_field(front_matter, "description")

            if not title or not date:
                # 使用檔名作為備用
                date_str = file_path.stem  # e.g., "2026-02-04"
                title = title or f"比特幣日報 - {date_str}"
                date = date or date_str

            return ArticleInfo(
                title=title.strip('"').strip("'"),
                date=date.strip(),
                description=(description or "").strip('"').strip("'"),
                filename=file_path.name,
            )

        except Exception as e:
            self.log.warning(f"文章解析失敗: {file_path.name}", error=str(e))
            return None

    def _extract_field(self, front_matter: str, field_name: str) -> Optional[str]:
        """從 Front Matter 提取欄位值"""
        pattern = rf"^{field_name}:\s*(.+)$"
        match = re.search(pattern, front_matter, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    def _update_news_table(
        self, content: str, articles: list[ArticleInfo]
    ) -> tuple[str, bool]:
        """更新最新快訊表格"""
        # 取最新 N 篇文章
        recent_articles = articles[: self.max_articles]

        # 建構新表格
        table_header = """| 日期 | 標題 | 摘要 |
|------|------|------|"""

        table_rows = [a.to_table_row() for a in recent_articles]
        new_table = table_header + "\n" + "\n".join(table_rows)

        # 尋找並替換現有表格
        # 匹配 "## 📰 最新快訊" 或類似標題下的表格
        news_section_pattern = r"(##\s*📰?\s*最新快訊[^\n]*\n+)((?:\|[^\n]+\n)+)"
        
        if re.search(news_section_pattern, content):
            new_content = re.sub(
                news_section_pattern,
                rf"\1{new_table}\n",
                content,
            )
            return new_content, new_content != content
        else:
            # 如果沒有現有表格，在適當位置插入
            # 在 "## 功能特色" 之前插入
            insert_section = f"""## 📰 最新快訊

{new_table}

"""
            # 尋找插入點 (在第一個 ## 之前，但在標題之後)
            first_section = re.search(r"\n##\s+", content)
            if first_section:
                insert_pos = first_section.start()
                new_content = content[:insert_pos] + "\n" + insert_section + content[insert_pos:]
                return new_content, True

            # 如果找不到，附加到末尾
            return content + "\n" + insert_section, True

    def _update_article_badge(
        self, content: str, article_count: int
    ) -> tuple[str, bool]:
        """更新文章數 Badge"""
        # Badge 格式: ![文章數](https://img.shields.io/badge/文章數-N篇-blue)
        badge_pattern = r"!\[文章數\]\(https://img\.shields\.io/badge/文章數-\d+篇-[^)]+\)"
        new_badge = f"![文章數](https://img.shields.io/badge/文章數-{article_count}篇-blue)"

        if re.search(badge_pattern, content):
            new_content = re.sub(badge_pattern, new_badge, content)
            return new_content, new_content != content
        else:
            # 在標題後面插入 Badge
            title_pattern = r"(#\s+CoinPilot AI[^\n]*\n)"
            if re.search(title_pattern, content):
                new_content = re.sub(
                    title_pattern,
                    rf"\1\n{new_badge}\n",
                    content,
                )
                return new_content, True

            return content, False

    async def add_article_to_readme(self, article: ArticleInfo) -> MaintainerResult:
        """
        新增單篇文章到 README (用於即時更新)
        
        Args:
            article: 文章資訊
            
        Returns:
            MaintainerResult: 維護結果
        """
        self.log.info("新增文章到 README", title=article.title)

        # 重新掃描並更新
        return await self.update_readme()

    def get_article_stats(self) -> dict:
        """取得文章統計資訊"""
        articles = self._scan_articles()

        if not articles:
            return {
                "total": 0,
                "latest_date": None,
                "oldest_date": None,
            }

        return {
            "total": len(articles),
            "latest_date": articles[0].date if articles else None,
            "oldest_date": articles[-1].date if articles else None,
            "recent_titles": [a.title for a in articles[:5]],
        }
