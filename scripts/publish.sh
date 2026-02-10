#!/bin/bash

# 一键发布到 PyPI 脚本
set -e

echo "🚀 一键发布 tts-tg-bot 到 PyPI"
echo "=============================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 检查是否在 GitHub Actions 环境
if [ -n "$GITHUB_ACTIONS" ]; then
    echo "🤖 检测到 GitHub Actions 环境"
    if [ -z "$PYPI_API_TOKEN" ] || [ -z "$TEST_PYPI_API_TOKEN" ]; then
        echo "❌ GitHub Actions 需要设置 PYPI_API_TOKEN 和 TEST_PYPI_API_TOKEN secrets"
        exit 1
    fi
else
    echo "💻 本地环境 - 需要输入令牌"
    
    # 检查是否有令牌文件
    if [ ! -f ~/.pypirc ] || ! grep -q "password" ~/.pypirc 2>/dev/null; then
        echo ""
        echo "📝 需要设置 PyPI 令牌"
        echo "请输入你的 TestPyPI API 令牌 (以 pypi- 开头):"
        read -s TEST_PYPI_TOKEN
        
        echo "请输入你的 PyPI API 令牌 (以 pypi- 开头):"
        read -s PYPI_TOKEN
        
        cat > ~/.pypirc << EOF
[distutils]
index-servers = 
    pypi
    testpypi

[pypi]
repository = https://upload.pypi.org/legacy/
username = __token__
password = $PYPI_TOKEN

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = $TEST_PYPI_TOKEN
EOF
        chmod 600 ~/.pypirc
        echo "✅ PyPI 令牌已保存"
    else
        echo "✅ 找到现有的 PyPI 配置"
    fi
fi

# 清理旧构建
echo ""
echo "🧹 清理旧构建..."
rm -rf dist/* build/* *.egg-info tts_bot.egg-info

# 构建包
echo ""
echo "📦 构建包..."
python3 -m build

echo ""
echo "📋 构建的包："
ls -lh dist/

# 检查包
echo ""
echo "🔍 检查包..."
python3 -m twine check dist/* || echo "⚠️  检查有警告，继续..."

# 本地环境：先发布到 TestPyPI 测试
if [ -z "$GITHUB_ACTIONS" ]; then
    echo ""
    echo "🧪 本地环境 - 先发布到 TestPyPI 测试..."
    python3 -m twine upload --repository testpypi dist/*
    
    if [ $? -eq 0 ]; then
        echo "✅ TestPyPI 发布成功!"
        echo ""
        read -p "TestPyPI 测试成功，是否继续发布到正式 PyPI? (y/n): " continue_pypi
        
        if [ "$continue_pypi" != "y" ]; then
            echo "🛑 用户取消发布到正式 PyPI"
            exit 0
        fi
    else
        echo "❌ TestPyPI 发布失败"
        exit 1
    fi
fi

# 发布到正式 PyPI
echo ""
echo "🚀 发布到正式 PyPI..."
python3 -m twine upload dist/*

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 成功发布到 PyPI!"
    echo "📦 包地址: https://pypi.org/project/tts-tg-bot/"
    echo ""
    echo "用户现在可以使用："
    echo "  pip install tts-tg-bot"
    echo "  tts-tg-bot --help"
else
    echo "❌ PyPI 发布失败"
    exit 1
fi
