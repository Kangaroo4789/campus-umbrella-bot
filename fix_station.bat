@echo off
cd /d C:\ClaudeWorkspace\機器人
C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe -c "import sqlite3; conn=sqlite3.connect('umbrella_v4.db'); conn.execute(\"UPDATE stations SET name='行政大樓' WHERE name='教學大樓'\"); conn.commit(); print('完成，異動', conn.total_changes, '筆'); conn.close()"
pause
