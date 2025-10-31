import asyncio
from playwright.async_api import async_playwright
from google import genai
from google.genai import types
import os

# --- 配置常量 ---
SCREENSHOT_PATH = "aol_screenshot_final.png"
AOL_URL = "https://www.aol.com/"
SCROLL_PAUSE_TIME = 1.5  # 滚动等待时间 (秒)
REAL_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
MODEL_NAME = 'gemini-2.5-flash'
OUTPUT_MARKDOWN_FILE = "aol_finance_news.md" 

# --- 步骤 1: Playwright 截图 (包含反爬虫和完整性优化) ---

async def capture_aol_screenshot():
    """使用 Playwright 捕获 AOL 首页的全屏截图，并优化完整性。"""
    print(f"--- 启动截图程序 ---")
    print(f"正在启动浏览器并访问 {AOL_URL}...")
    
    async with async_playwright() as p:
        # 启动浏览器并设置反爬虫配置
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=REAL_USER_AGENT,
            viewport={'width': 1920, 'height': 1080}
        )

        # 注入 JavaScript，禁用 navigator.webdriver 标志 (反爬虫关键)
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            })
        """)
        
        page = await context.new_page()

        print("导航到 AOL 首页...")
        await page.goto(AOL_URL, wait_until="domcontentloaded") 
        await page.wait_for_timeout(3000) # 强制等待3秒让页面稳定

        # 渐进式滚动以触发懒加载
        print("开始渐进式滚动以加载全部内容...")
        last_height = 0
        while True:
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(int(SCROLL_PAUSE_TIME * 1000))

            new_height = await page.evaluate('document.body.scrollHeight')
            
            if new_height == last_height:
                print("已到达页面底部，内容加载完毕。")
                break
            
            last_height = new_height
            # 模拟人类行为：滚动到中间再滚到底部
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
            await page.wait_for_timeout(500)
            print(f"滚动并加载新内容... 当前高度: {new_height}px")

        # 截图
        await page.evaluate('window.scrollTo(0, 0);')
        await page.wait_for_timeout(1000) 
        
        print(f"开始捕获全页截图至: {SCREENSHOT_PATH}...")
        await page.screenshot(path=SCREENSHOT_PATH, full_page=True)
        print(f"🎉 截图完成。文件大小: {os.path.getsize(SCREENSHOT_PATH) / (1024*1024):.2f} MB")

        await browser.close()
        
    return os.path.abspath(SCREENSHOT_PATH)

# --- 步骤 2: Gemini API 分析 (使用文件上传模式并保存结果) ---

def analyze_and_translate_news(image_path):
    """
    使用 Gemini 模型分析截图，通过 client.files.upload 提取、翻译新闻并保存到 Markdown 文件。
    """
    if "GEMINI_API_KEY" not in os.environ:
        print("❌ 错误：请设置环境变量 GEMINI_API_KEY")
        return
        
    if not os.path.exists(image_path):
        print(f"❌ 错误：未找到图片文件：{image_path}。")
        return

    print(f"\n--- 启动 Gemini 分析程序 ---")
    print(f"正在连接 Gemini API 并准备分析图片...")
    
    client = genai.Client()
    uploaded_file = None 

    try:
        # 1. 🌟 上传本地文件到 Gemini 服务 (修正：移除 mime_type)
        print(f"上传文件: {image_path}")
        uploaded_file = client.files.upload(
            file=image_path 
        )
        print(f"文件上传成功。文件名称: {uploaded_file.name}")

        # 2. 准备 Prompt
        prompt = (
            "请仔细查看这张 AOL 首页截图。\n"
            "你的任务是：\n"
            "1. **识别和提取**图片中所有的**新闻标题**。\n"
            "2. **忽略**广告等非新闻内容。\n"
            "3. **将提取到的英文标题按内容分类**。\n"
            "4. **将提取到的英文标题翻译成中文**。\n"
            "5. 请以清晰的 Markdown 格式输出，每一项都是 '英文标题' -> '中文翻译' 的形式。"
        )

        # 3. 调用 Gemini 模型
        print("发送请求到 Gemini 模型...")
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[prompt, uploaded_file], 
        )

        # 4. 输出结果
        markdown_content = response.text
        print("\n--- 🤖 Gemini 财经新闻提取和翻译结果 ---")
        print(markdown_content)
        print("------------------------------------------")
        
        # 5. 🌟 将 Markdown 内容保存到本地文件
        try:
            with open(OUTPUT_MARKDOWN_FILE, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            print(f"\n✅ Markdown 内容已成功保存到文件: {OUTPUT_MARKDOWN_FILE}")
        except IOError as e:
            print(f"\n❌ 写入文件时发生错误: {e}")

    except Exception as e:
        print(f"在调用 Gemini API 时发生错误: {e}")
    finally:
        # 6. 清理：删除已上传的文件
        if uploaded_file:
            print(f"\n正在删除上传的文件: {uploaded_file.name}...")
            try:
                client.files.delete(name=uploaded_file.name)
                print("文件删除成功。")
            except Exception as e:
                 print(f"清理文件时发生错误: {e}")


# --- 主函数 ---
async def main():
    # 运行截图
    screenshot_path_abs = await capture_aol_screenshot()
    
    # 运行分析
    analyze_and_translate_news(screenshot_path_abs)

if __name__ == "__main__":
    asyncio.run(main())
