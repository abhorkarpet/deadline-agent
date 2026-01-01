# Release v3.0.0

## 🎉 What's New

### Page Footer
Added a professional footer at the bottom of the page that displays:
- **Version Information**: Shows "Deadline Agent v3.0.0"
- **About Us Link**: Clickable link to contact us at smartretireai@gmail.com

The footer provides a clean, professional appearance and easy access to contact information.

## 🐛 Bug Fixes

### Welcome Page Stability
Fixed a critical issue where the welcome page would reappear every time any widget on the page was interacted with.

**What was fixed:**
- Welcome page now only shows once per session
- Stays dismissed after clicking "I understand, continue →"
- No longer reappears when changing text inputs, number inputs, or other widgets
- Improved session state management

**Technical details:**
- Separated checkbox state from welcome suppression logic
- Only updates welcome suppression when the continue button is clicked
- Enhanced session state persistence across reruns

## 📦 Installation

```bash
pip install -r requirements.txt
streamlit run deadline_agent_app.py
```

## 🔗 Links

- **About Us**: [smartretireai@gmail.com](mailto:smartretireai@gmail.com)
- **Documentation**: See README.md for full setup instructions

## 🙏 Thank You

Thank you for using Deadline Agent! If you encounter any issues or have feedback, please reach out to us at smartretireai@gmail.com.

