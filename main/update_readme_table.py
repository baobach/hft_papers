import pandas as pd
from datetime import datetime
import re

CSV_PATH = "hft_papers/papers.csv"
README_PATH = "README.md"
TABLE_HEADER = (
    "| Paper | Author(s) | Description | Source | Date |\n"
    "| --- | --- | --- | --- | --- |\n"
)

# Read CSV and get top 20 most recent papers
def get_top_papers(csv_path, n=20):
    df = pd.read_csv(csv_path)
    # Parse date, sort descending
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.sort_values("Date", ascending=False)
    df = df.head(n)
    # Fill NaN with empty string
    df = df.fillna("")
    return df

def build_table(df):
    lines = [TABLE_HEADER]
    for _, row in df.iterrows():
        lines.append(
            f"| {row['Paper']} | {row['Author(s)']} | {row['Description']} | {row['Source']} | {row['Date'].date() if row['Date'] else ''} |"
        )
    return "\n".join(lines)

def replace_table_in_readme(readme_path, new_table):
    with open(readme_path, encoding="utf-8") as f:
        content = f.read()
    # Regex to find the table section
    pattern = re.compile(r'(## Most recent HFT papers\n\n\| Paper \| Author\(s\) \| Description \| Source \| Date \|\n\| --- \| --- \| --- \| --- \| --- \|\n)([\s\S]*?)(?=\n#|\n##|\n\Z)', re.MULTILINE)
    # Replace the table section
    new_content = re.sub(pattern, r'\1' + new_table + '\n', content)
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)

if __name__ == "__main__":
    df = get_top_papers(CSV_PATH, n=20)
    table = build_table(df)
    replace_table_in_readme(README_PATH, table)
