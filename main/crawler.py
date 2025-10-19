
import argparse
from datetime import datetime
import sys
from typing import Any, Dict, List, Optional, Set
import csv
import os
import requests
from bs4 import BeautifulSoup


URL = (
    "https://www.paperdigest.org/2020/04/recent-papers-on-algorithmic-trading-high-frequency-trading/"
)


def _safe_text(el) -> str:
    return el.get_text(strip=True) if el else ""


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse a date string like 'YYYY-MM-DD' to datetime; return None if unknown."""
    if not date_str:
        return None
    # Common formats on PaperDigest are ISO like 2025-10-10
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def extract_rows(table) -> List[Dict[str, Any]]:
    rows = table.find_all("tr")
    if not rows:
        return []
    # Skip header row
    data_rows = rows[1:]
    out: List[Dict[str, Any]] = []

    for row in data_rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            # Unexpected row shape; skip
            continue

        # Title and description are in the 2nd column (index 1)
        title_cell = cols[1]
        # Prefer the first anchor that is not the "View" link
        anchors = title_cell.find_all("a", href=True)
        paper_tag = None
        for a in anchors:
            if _safe_text(a).strip().lower() != "view":
                paper_tag = a
                break
        if paper_tag is None and anchors:
            paper_tag = anchors[0]
        paper_name = _safe_text(paper_tag)

        # Authors in 3rd column (index 2)
        author_cell = cols[2]
        author_links = author_cell.find_all("a")
        if author_links:
            authors = "; ".join([_safe_text(a) for a in author_links])
        else:
            authors = _safe_text(author_cell)
        if authors.startswith(";"):
            authors = authors.lstrip(";").strip() + " et. al."

        # Description (italic highlight) in title cell
        highlight = title_cell.find("i")
        description = _safe_text(highlight).replace("Highlight: ", "") if highlight else ""


        # Source link: look for the anchor with text 'View' (case-insensitive)
        view_tag = None
        for a in anchors:
            if _safe_text(a).strip().lower() == "view":
                view_tag = a
                break
        # Try to build a readable source name; fallback to last path/identifier
        source_link = view_tag.get("href") if view_tag else (paper_tag.get("href") if paper_tag else "")
        source_name = "N/A"
        if paper_tag and paper_tag.get("href"):
            href = paper_tag.get("href")
            if "paper_id=" in href:
                source_name = href.split("paper_id=")[-1]
            else:
                source_name = href.rstrip("/").split("/")[-1] or "Unknown"
        source_md = f"[{source_name}]({source_link})" if source_link else "N/A"

        # Date is in 5th column (index 4)
        date_str = _safe_text(cols[4])
        date_obj = parse_date(date_str)


        out.append(
            {
                "paper": paper_name,
                "authors": authors,
                "description": description,
                "source": source_md,
                "source_link": source_link,
                "date": date_str,
                "date_obj": date_obj,
            }
        )

    return out


def build_markdown(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "| Paper | Author(s) | Description | Source | Date |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['paper']} | {r['authors']} | {r['description']} | {r['source']} | {r['date']} |"
        )
    return "\n".join(lines)

def build_csv(rows: List[Dict[str, Any]]) -> str:
    # Output as CSV string
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Paper", "Author(s)", "Description", "Source", "Source Link", "Date"])
    for r in rows:
        writer.writerow([
            r["paper"],
            r["authors"],
            r["description"],
            r["source"],
            r["source_link"],
            r["date"],
        ])
    return output.getvalue()


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def read_existing_papers(file_path: str, fmt: str = "md") -> Set[str]:
    """Read existing papers file and return set of unique source links."""
    seen_links = set()
    if not os.path.exists(file_path):
        return seen_links
    if fmt == "csv":
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                link = row.get("Source Link") or row.get("source_link")
                if link:
                    seen_links.add(link.strip())
    else:
        # Markdown: parse lines like | ... | ... | ... | [name](link) | ... |
        import re
        for line in open(file_path, encoding="utf-8"):
            m = re.search(r"\[.*?\]\((http[^)]+)\)", line)
            if m:
                seen_links.add(m.group(1).strip())
    return seen_links

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Scrape PaperDigest algorithmic trading table and print most recent papers first."
        )
    )
    parser.add_argument(
        "--url",
        default=URL,
        help="Source URL containing the papers table",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Only include papers on/after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of rows printed (after sorting)",
    )
    parser.add_argument(
        "--append",
        default=None,
        help="Path to existing papers file to append to (deduplicate by source link)",
    )
    parser.add_argument(
        "--format",
        choices=["md", "csv"],
        default="md",
        help="Output format: md (Markdown) or csv (CSV)",
    )

    args = parser.parse_args()

    html = fetch_html(args.url)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        print("No table found on the webpage.", file=sys.stderr)
        sys.exit(1)


    rows = extract_rows(table)

    # Sort by date descending; rows with unknown dates go last
    rows.sort(key=lambda r: (r["date_obj"] is None, r["date_obj"] or datetime.min), reverse=False)
    rows = list(reversed(rows))

    # Optional filtering by since date
    if args.since:
        since_dt = parse_date(args.since)
        if since_dt:
            rows = [r for r in rows if r["date_obj"] and r["date_obj"] >= since_dt]

    # Deduplicate and append to existing file if requested
    if args.append:
        seen_links = read_existing_papers(args.append, fmt=args.format)
        # Only keep new rows whose source_link is not in seen_links
        new_rows = [r for r in rows if r["source_link"] and r["source_link"] not in seen_links]
        # Read all existing rows (for output)
        all_rows = []
        if os.path.exists(args.append):
            if args.format == "csv":
                with open(args.append, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        all_rows.append({
                            "paper": row.get("Paper", ""),
                            "authors": row.get("Author(s)", ""),
                            "description": row.get("Description", ""),
                            "source": row.get("Source", ""),
                            "source_link": row.get("Source Link", ""),
                            "date": row.get("Date", ""),
                            "date_obj": parse_date(row.get("Date", "")),
                        })
            else:
                # Markdown: parse table rows
                import re
                with open(args.append, encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("| ") and not line.startswith("| ---"):
                            # Split columns
                            cols = [c.strip() for c in line.strip().split("|")[1:-1]]
                            if len(cols) >= 5:
                                # Extract source link from [name](link)
                                m = re.search(r"\[(.*?)\]\((http[^)]+)\)", cols[3])
                                source_link = m.group(2) if m else ""
                                all_rows.append({
                                    "paper": cols[0],
                                    "authors": cols[1],
                                    "description": cols[2],
                                    "source": cols[3],
                                    "source_link": source_link,
                                    "date": cols[4],
                                    "date_obj": parse_date(cols[4]),
                                })
        # Combine: new rows first, then all previous rows (to keep newest at top)
        combined = new_rows + all_rows
        # Remove duplicates (keep first occurrence)
        seen = set()
        deduped = []
        for r in combined:
            link = r["source_link"]
            if link and link not in seen:
                deduped.append(r)
                seen.add(link)
        # Optional limit
        if args.limit is not None and args.limit > 0:
            deduped = deduped[: args.limit]
        # Output to file (overwrite)
        if args.format == "csv":
            with open(args.append, "w", encoding="utf-8", newline="") as f:
                f.write(build_csv(deduped))
        else:
            with open(args.append, "w", encoding="utf-8") as f:
                f.write(build_markdown(deduped))
        print(f"Appended {len(new_rows)} new papers. Total: {len(deduped)}.")
    else:
        # Optional limit
        if args.limit is not None and args.limit > 0:
            rows = rows[: args.limit]
        # Output
        if args.format == "csv":
            print(build_csv(rows))
        else:
            print(build_markdown(rows))


if __name__ == "__main__":
    main()
    