# AI Coding Agent Instructions for Umbrella Sharing LINE Bot

## Project Overview
This is a Flask-based LINE bot implementing an optimistic verification umbrella borrowing system for university campus use. The system prioritizes trust and convenience over strict verification.

## Architecture
- **Main App**: `app.py` - Single-file Flask application handling LINE webhook, user management, and photo storage
- **Database**: SQLite (`umbrella.db`) with `users` (user_id, status, credit, real_name, student_id_path, umbrella_id, borrow_time) and `stations` (id, name, umbrella_count, image_url) tables
- **User State Machine**: 7-state FSM (unregistered → wait_name → wait_id_card → idle → wait_umbrella_id → borrowing → ready_to_return → idle)
- **Photo Storage**: `uploads/` directory for user-uploaded images (student IDs and return verification photos)
- **Background Processing**: Threading for YOLO AI verification and overdue penalty scheduler
- **External Integration**: LINE Bot API for messaging, Flex Messages for admin dashboard

## Key Patterns
- **Optimistic Verification**: Return process completes immediately upon photo upload, assuming good faith (core research concept); AI verification runs asynchronously in background thread
- **Command-Based Interface**: Text commands in Chinese: "註冊" (register), "借傘" (borrow), "還傘" (return); admin commands use regex patterns like "管理 {umbrella_id}" and "執行處罰 {umbrella_id} {delta} {reason}"
- **State Management**: Strict FSM transitions with credit scoring (60+ required to borrow, penalties for overdue/late returns)
- **Photo Naming**: `uploads/{user_id}_{message_id}.jpg` for uploaded images
- **Chinese UI**: All user messages use Traditional Chinese with emojis for friendly tone
- **Admin System**: Regex-based admin commands with Flex Message dashboards for penalty management

## Development Workflow
- **Local Testing**: `python app.py` runs on port 5000 with auto DB init and background threads
- **Public Exposure**: Use `ngrok.exe http 5000` to create webhook URL for LINE Developers console
- **Debugging**: Check `uploads/` folder for uploaded images, monitor console for webhook events and background thread logs
- **Database**: SQLite file `umbrella.db` created automatically; inspect with any SQLite browser
- **No Build Process**: Pure Python script, no compilation or complex setup

## Code Style
- **Language**: Python 3 with Flask framework
- **Comments**: Mixed English/Chinese, functional sections clearly marked with emojis and separators
- **Error Handling**: Basic try/catch for webhook signature validation and background processes
- **Database**: Direct SQLite operations with context managers (`with get_conn() as conn`)
- **Dependencies**: Minimal - `flask`, `line-bot-sdk`, `ultralytics` (for YOLO), `sqlite3` (built-in)

## Integration Points
- **LINE Bot API**: Webhook at `/callback`, handles text/image messages and follow events
- **YOLO AI**: Asynchronous umbrella detection in return photos using `yolov8n.pt` model
- **File I/O**: Direct photo saving to local filesystem with timestamp-based naming
- **Threading**: Background threads for overdue checking (60s intervals) and AI verification

## Common Tasks
- **Add New Commands**: Extend `handle_text()` with new status checks and `elif` branches for new Chinese keywords
- **Modify Messages**: Update reply strings in respective state handlers within `handle_text()`
- **Photo Processing**: Enhance `verify_return_image()` for actual image analysis (currently just saves and detects umbrellas)
- **User Persistence**: Replace in-memory state with persistent storage if needed (currently uses SQLite)
- **Admin Features**: Add new regex patterns in `handle_admin_commands()` and corresponding Flex Message builders