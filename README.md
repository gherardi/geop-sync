# GEOP Sync

Synchronize your GEOP lectures with your Google Calendar through web scraping and automation.

## Overview

This script automates the process of scraping your GEOP portal for upcoming lectures and synchronizes them with your Google Calendar. It ensures your calendar is always up-to-date with the latest lecture schedule, saving you time and reducing manual entry errors.

## Features

- Automated login and scraping of the GEOP portal
- Extraction and parsing of lecture data (subject, time, classroom, professor, etc.)
- Synchronization of lectures with a Supabase database
- Creation, update, and deletion of Google Calendar events for your lectures
- Robust error handling and logging

## Requirements

- Python 3.8+
- Google Calendar account and a service account with access to your calendar
- Supabase project and table for storing lectures
- Chrome browser (for Selenium WebDriver)

## Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/gherardi/geop-sync.git
   cd geop-sync-scraper
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Prepare environment variables**
   Create a `.env` file in the project root with the following variables:

   ```env
   PORTAL_URL=<your_geop_portal_url>
   USER_EMAIL=<your_geop_email>
   USER_PASSWORD=<your_geop_password>
   SUPABASE_URL=<your_supabase_url>
   SUPABASE_ANON_KEY=<your_supabase_anon_key>
   GOOGLE_CALENDAR_ID=<your_google_calendar_id>
   GOOGLE_SERVICE_ACCOUNT_FILE=<path_to_your_service_account_json>
   ```

4. **Google Service Account Setup**

   - Create a Google Cloud project and enable the Google Calendar API.
   - Create a service account and download the JSON credentials file.
   - Share your Google Calendar with the service account email (with edit permissions).

5. **Supabase Setup**
   - Create a Supabase project.
   - Create a `lectures` table with columns: `id`, `subject`, `date`, `start_time`, `end_time`, `classroom`, `professor`, `calendar_event_id`.

## Usage

Run the script with:

```bash
python main.py
```

The script will:

1. Validate your configuration.
2. Delete all future lectures and their calendar events.
3. Scrape new lectures from the GEOP portal.
4. Save them to Supabase.
5. Create Google Calendar events for each lecture.

## Troubleshooting

- **WebDriver errors**: Ensure Chrome is installed and compatible with `webdriver-manager`.
- **Google Calendar errors**: Make sure the service account has access to your calendar.
- **Supabase errors**: Double-check your Supabase URL, anon key, and table schema.
- **Environment variables**: All required variables must be set in your `.env` file.

## Logging

Logs are output to the console with timestamps and severity levels. Check logs for detailed error messages if something goes wrong.

<!-- ## License -->

<!-- MIT License. See `LICENSE` file for details. -->
