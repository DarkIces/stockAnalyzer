@echo off
setx SMTP_SERVER "smtp.gmail.com"
setx SMTP_PORT "587"
:: 请将下面的密码替换为您的Email地址
setx SENDER_EMAIL "abc@gmail.com"
:: 请将下面的密码替换为您的应用专用密码
setx SENDER_PASSWORD ""

echo 环境变量设置完成！
echo 请重新打开命令提示符或PowerShell窗口以使更改生效。
pause 