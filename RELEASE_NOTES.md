# Release Notes

## Version 3.0.0

### 🎉 New Features

- **Page Footer**: Added a professional footer at the bottom of the page displaying the version number and an "About Us" link
  - Footer includes version information (Deadline Agent v3.0.0)
  - "About Us" link points to smartretireai@gmail.com for contact and inquiries

### 🐛 Bug Fixes

- **Welcome Page Stability**: Fixed an issue where the welcome page would reappear whenever any widget on the page was interacted with
  - Separated checkbox state from welcome suppression logic
  - Welcome page now only shows once per session and stays dismissed after clicking "Continue"
  - Improved session state management to prevent unwanted reruns

### 🔧 Technical Improvements

- Enhanced session state persistence across page reruns
- Improved user experience with more stable UI behavior
- Better separation of concerns in welcome page logic

---

## Version 2.0.0

### 🎉 New Features

- **Date-based Scan Window**: Added support for scanning emails from a specific start date
  - Choose between "Last N days" or "Start date" scan window modes
  - More flexible email scanning options

- **LLM Cost Confirmation**: Added cost estimation and confirmation dialog before running LLM extraction
  - Shows estimated cost based on actual email count
  - Allows users to skip LLM extraction if desired
  - Option to "Don't remind me again" for future scans

### 🔧 Technical Improvements

- Improved cost tracking and transparency
- Better user control over LLM usage and costs

---

## Version 1.1.0

### 🎉 New Features

- **App Password Clarification**: Added clear instructions explaining that app passwords are NOT regular passwords
  - Expanded help sections for Gmail and other email providers
  - Step-by-step instructions for generating app passwords

- **Browser Recommendation**: Added recommendation to use Chrome browser on Desktop for optimal performance

### 📝 Documentation

- Improved user guidance for email authentication setup
- Better clarity on authentication requirements

---

## Previous Versions

### Version 1.0.0

Initial release with core features:
- Email scanning via IMAP
- Deadline detection using regex patterns
- Calendar export (.ics files)
- Feedback learning system
- Basic categorization

