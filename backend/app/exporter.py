from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


def generate_social_share_card(
    session_id: str, report: dict, output_root: str = "/data/sessions"
) -> str:
    width, height = 1200, 630
    image = Image.new("RGB", (width, height), "#f4f3ee")
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 32)
        score_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 104)
        label_font = ImageFont.truetype("DejaVuSans.ttf", 17)
        body_font = ImageFont.truetype("DejaVuSans.ttf", 25)
    except OSError:
        title_font = score_font = label_font = body_font = ImageFont.load_default()

    draw.rectangle((0, 0, 18, height), fill="#d95d39")
    draw.text((64, 54), "INTERVIEWRUNWAY   /   INTERVIEW REVIEW", fill="#243b35", font=label_font)
    draw.line((64, 92, 1136, 92), fill="#c9cec4", width=2)
    draw.text((64, 130), "COMMUNICATION SCORE", fill="#65736b", font=label_font)
    score = report.get("communication_score")
    draw.text((60, 168), str(score) if score is not None else "N/A", fill="#243b35", font=score_font)
    if score is not None:
        draw.text((330, 236), "/ 100", fill="#d95d39", font=body_font)
    draw.text((650, 144), "APPROACH", fill="#65736b", font=label_font)
    persona = str(report.get("structural_classification", "REVIEW PENDING")).replace("_", " ").title()
    draw.text((650, 178), persona, fill="#243b35", font=title_font)
    draw.text((64, 398), "COACHING NOTE", fill="#65736b", font=label_font)
    summary = str(report.get("critique_summary", ""))
    for index, line in enumerate(wrap(summary, width=74)[:3]):
        draw.text((64, 434 + index * 36), line, fill="#243b35", font=body_font)
    draw.text((64, 568), "INTERVIEWRUNWAY  /  PRACTICE WITH INTENTION", fill="#65736b", font=label_font)

    output_dir = Path(output_root) / session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "share_card.png"
    image.save(destination)
    return str(destination)