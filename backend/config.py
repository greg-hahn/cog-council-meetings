import os


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/council_meetings",
)

# For SQLAlchemy async compatibility, strip "postgresql+asyncpg://" etc.
# We use synchronous psycopg2 for simplicity.
SQLALCHEMY_DATABASE_URL = DATABASE_URL

GUELPH_ESCRIBE_BASE = "https://pub-guelph.escribemeetings.com"
GUELPH_AGENDA_HUB = (
    "https://guelph.ca/city-hall/mayor-and-council/city-council/agendas-and-minutes/"
)
GUELPH_LIVESTREAM_URL = "https://guelph.ca/news/live/"

# LLM summarization (optional — falls back to keyword matching if unset)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# eScribe discovery
GUELPH_MEETING_TYPES = ["City Council", "Committee of the Whole", "Council Planning"]
GUELPH_CALENDAR_URL = (
    "https://pub-guelph.escribemeetings.com/MeetingsCalendarView.aspx/PastMeetings"
)
