#!/usr/bin/env python3
"""
Bot路由服务 - 根据路径代理到不同的ttyd端口
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error

class BotRouterHandler(BaseHTTPRequestHandler):
    # Bot配置 - 路径映射到ttyd端口
    BOTS = {
        'bot1': {
            'name': 'Kiro TTS Bot 1',
            'username': '@kiro_tts_test_1770989796_bot',
            'ttyd_port': 7680,
            'description': '语音转文字 + AI对话'
        },
        'bot2': {
            'name': 'Kiro TTS Bot 2',
            'username': '@bot2_username',
            'ttyd_port': 7681,
            'description': 'Bot 2'
        },
        'bot3': {
            'name': 'Kiro TTS Bot 3',
            'username': '@bot3_username',
            'ttyd_port': 7682,
            'description': 'Bot 3'
        },
        'bot4': {
            'name': 'Kiro TTS Bot 4',
            'username': '@bot4_username',
            'ttyd_port': 7683,
            'description': 'Bot 4'
        }
    }
    
    def do_GET(self):
        path = self.path.strip('/').split('?')[0]
        
        # 首页 - 显示所有Bot
        if not path:
            self.show_bot_list()
            return
        
        # Bot页面 - 代理到ttyd
        if path in self.BOTS:
            self.proxy_to_ttyd(path)
            return
        
        self.send_error(404, 'Bot not found')
    
    def proxy_to_ttyd(self, bot_id):
        """代理请求到ttyd端口"""
        bot = self.BOTS[bot_id]
        ttyd_port = bot['ttyd_port']
        
        # 移除bot_id前缀，保留剩余路径
        remaining_path = self.path[len(bot_id)+1:]  # 去掉 /bot1
        if not remaining_path:
            remaining_path = '/'
        
        target_url = f'http://localhost:{ttyd_port}{remaining_path}'
        
        try:
            # 创建请求
            req = urllib.request.Request(target_url, method=self.command)
            
            # 复制请求头
            for key, value in self.headers.items():
                if key.lower() not in ['host', 'connection']:
                    req.add_header(key, value)
            
            # 发送请求
            with urllib.request.urlopen(req, timeout=30) as response:
                # 发送响应状态
                self.send_response(response.status)
                
                # 复制响应头
                for key, value in response.headers.items():
                    if key.lower() not in ['connection', 'transfer-encoding']:
                        self.send_header(key, value)
                self.end_headers()
                
                # 发送响应体
                self.wfile.write(response.read())
                
        except Exception as e:
            self.send_error(502, f'Proxy Error: {str(e)}')
    
    def show_bot_list(self):
        html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kiro Bots</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { color: white; text-align: center; margin-bottom: 40px; font-size: 2.5em; }
        .bot-card {
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: transform 0.3s;
        }
        .bot-card:hover { transform: translateY(-5px); }
        .bot-card h2 { color: #667eea; margin-bottom: 10px; }
        .bot-card p { color: #666; margin-bottom: 15px; }
        .btn {
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 30px;
            border-radius: 25px;
            text-decoration: none;
            margin-right: 10px;
            transition: transform 0.3s;
        }
        .btn:hover { transform: scale(1.05); }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Kiro Bots</h1>
'''
        for bot_id, bot in self.BOTS.items():
            html += f'''
        <div class="bot-card">
            <h2>{bot['name']}</h2>
            <p>{bot['description']}</p>
            <p><strong>Username:</strong> {bot['username']}</p>
            <p><strong>TTY Port:</strong> {bot['ttyd_port']}</p>
            <a href="/{bot_id}" class="btn">💻 打开终端</a>
        </div>
'''
        html += '''
    </div>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode())
    
    
    def log_message(self, format, *args):
        print(f"[BotRouter] {self.address_string()} - {format % args}")

def run_server(port=12345):
    server = HTTPServer(('0.0.0.0', port), BotRouterHandler)
    print(f"🤖 Bot路由服务启动在端口 {port}")
    print(f"   访问: http://localhost:{port}")
    server.serve_forever()

if __name__ == '__main__':
    run_server()
