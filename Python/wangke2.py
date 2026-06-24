from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import sys
import os
import requests
import json
import re
import random


class CourseAutoPlayer:
    def __init__(self, driver_path="chromedriver.exe"):
        self.driver_path = driver_path
        self.driver = None
        self.sesskey = None
        self.current_course_id = None
        self.setup_driver(driver_path)

        # 创建requests session用于API调用
        self.session = requests.Session()

    def setup_driver(self, driver_path):
        """初始化浏览器"""
        if not os.path.exists(driver_path):
            print(f"❌ 找不到 ChromeDriver: {driver_path}")
            print("请确保：")
            print("1. ChromeDriver 已下载并放在指定路径")
            print("2. ChromeDriver 版本与 Chrome 浏览器版本匹配")
            print("3. 路径中没有中文或特殊字符")
            sys.exit(1)

        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        service = Service(self.driver_path)
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.maximize_window()

        # 隐藏 webdriver 特征
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => false});"
            },
        )

        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

    def login(self, username, password):
        """登录系统"""
        print("开始登录...")

        # 访问登录页面
        self.driver.get(
            "https://authserver.gdut.edu.cn/authserver/login?service=https%3A%2F%2Fcourses.gdut.edu.cn%2Fauth%2Fsso%2Flogin.php"
        )

        # 等待页面加载
        time.sleep(3)

        try:
            # 输入用户名密码
            username_input = self.driver.find_element(By.ID, "username")
            password_input = self.driver.find_element(By.ID, "password")

            username_input.send_keys(username)
            password_input.send_keys(password)
            print("✅ 账号密码输入完成")

            # 点击登录按钮
            login_button = self.driver.find_element(By.ID, "login_submit")
            login_button.click()
            print("✅ 已点击登录按钮")

            # 等待登录完成，检查是否跳转到课程页面
            WebDriverWait(self.driver, 15).until(EC.url_contains("courses.gdut.edu.cn"))
            print("✅ 登录成功！")

            # 将浏览器cookie同步到requests session
            cookies = self.driver.get_cookies()
            for cookie in cookies:
                self.session.cookies.set(cookie["name"], cookie["value"])

            return True

        except Exception as e:
            print(f"❌ 登录过程中出错: {e}")
            return False

    def get_sesskey(self):
        """从当前页面获取sesskey"""
        try:
            # 方法1: 从JavaScript变量中获取
            sesskey_script = """
            if (typeof M !== 'undefined' && M.cfg && M.cfg.sesskey) {
                return M.cfg.sesskey;
            }
            return null;
            """
            sesskey = self.driver.execute_script(sesskey_script)

            if sesskey:
                self.sesskey = sesskey
                return sesskey

            # 方法2: 从页面源代码中正则匹配
            page_source = self.driver.page_source
            patterns = [
                r'"sesskey":"([^"]+)"',
                r"sesskey['\"]?\\s*[:=]\\s*['\"]([^'\"]+)",
                r"M\\.cfg\\s*=\\s*{[^}]*sesskey['\"]?\\s*:\\s*['\"]([^'\"]+)",
            ]

            for pattern in patterns:
                match = re.search(pattern, page_source)
                if match:
                    self.sesskey = match.group(1)
                    return self.sesskey

            print("❌ 无法获取sesskey")
            return None

        except Exception as e:
            print(f"❌ 获取sesskey时出错: {e}")
            return None

    def get_course_id_from_url(self, url):
        """从URL中提取课程ID"""
        match = re.search(r"id=(\d+)", url)
        if match:
            return match.group(1)
        return None

    def get_course_data(self, course_url):
        """获取指定课程的JSON数据"""
        print(f"\n📚 正在获取课程数据: {course_url}")

        try:
            # 访问课程页面
            self.driver.get(course_url)
            time.sleep(3)

            # 获取课程ID
            course_id = self.get_course_id_from_url(course_url)
            if not course_id:
                print(f"❌ 无法从URL中提取课程ID: {course_url}")
                return None

            self.current_course_id = course_id

            # 获取sesskey
            sesskey = self.get_sesskey()
            if not sesskey:
                print("❌ 无法获取sesskey")
                return None

            print(f"✅ 获取到sesskey: {sesskey}")
            print(f"✅ 课程ID: {course_id}")

            # 构造API请求
            api_url = f"https://courses.gdut.edu.cn/lib/ajax/service.php?sesskey={sesskey}&info=core_courseformat_get_state"

            payload = [
                {
                    "index": 0,
                    "methodname": "core_courseformat_get_state",
                    "args": {"courseid": int(course_id)},
                }
            ]

            headers = {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": course_url,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }

            # 发送API请求
            response = self.session.post(api_url, json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                if data and data[0].get("error") == False:
                    course_data = json.loads(data[0]["data"])
                    print(
                        f"✅ 成功获取课程数据，共 {len(course_data.get('section', []))} 个章节"
                    )
                    return course_data
                else:
                    print(f"❌ API返回错误: {data}")
            else:
                print(f"❌ API请求失败，状态码: {response.status_code}")

        except Exception as e:
            print(f"❌ 获取课程数据时出错: {e}")

        return None

    def extract_mp4_resources(self, course_data):
        """从课程数据中提取所有.mp4资源信息"""
        resources = []

        if not course_data or "section" not in course_data:
            return resources

        # 创建cm_id到cm信息的映射
        cm_map = {}
        for cm in course_data.get("cm", []):
            cm_map[cm["id"]] = cm

        # 遍历所有章节
        for section in course_data.get("section", []):
            section_title = section.get("title", "未知章节")
            section_number = section.get("number", 0)

            # 跳过常规章节（通常是公告区）
            if section_number == 0 and section_title == "常规":
                continue

            print(f"\n📖 章节 {section_number}: {section_title}")

            # 遍历章节中的所有内容模块
            for cm_id in section.get("cmlist", []):
                cm_info = cm_map.get(str(cm_id))
                if cm_info:
                    name = cm_info.get("name", "")
                    modname = cm_info.get("modname", "")
                    # 只处理资源库文件
                    if not name.lower().endswith(".pptx") and modname == "资源库文件":
                        # 从URL中提取fsresourceid
                        url = cm_info.get("url", "")
                        fsresourceid_match = re.search(r"id=(\d+)", url)
                        fsresourceid = (
                            fsresourceid_match.group(1) if fsresourceid_match else None
                        )

                        resource_info = {
                            "section_id": section["id"],
                            "section_title": section_title,
                            "url": url,
                            "completed": cm_info.get("completionstate", 0) == 1,
                            "cmid": cm_id,
                            "fsresourceid": fsresourceid,
                        }
                        resources.append(resource_info)

                        status_icon = "✅" if resource_info["completed"] else "❌"
                        print(f"  {status_icon} {modname}: {name} (ID: {fsresourceid})")

        return resources

    def get_all_courses_resources(self, course_urls):
        """获取所有课程的资源并返回统一数组"""
        all_resources = []

        for i, course_url in enumerate(course_urls, 1):
            print(f"\n{'='*50}")
            print(f"处理第 {i}/{len(course_urls)} 门课程")
            print(f"{'='*50}")

            # 获取课程数据
            course_data = self.get_course_data(course_url)

            if course_data:
                # 提取资源
                resources = self.extract_mp4_resources(course_data)

                # 为每个资源添加课程ID
                course_id = self.get_course_id_from_url(course_url)
                for resource in resources:
                    resource["course_id"] = course_id
                    resource["course_url"] = course_url

                all_resources.extend(resources)
                print(f"✅ 课程 {course_id} 找到 {len(resources)} 个资源文件")
            else:
                print(f"❌ 无法获取课程 {course_url} 的数据")

            # 短暂休息，避免请求过于频繁
            time.sleep(2)

        return all_resources

    def analyze_resources(self, all_resources):
        """分析资源数据"""
        print(f"\n{'='*60}")
        print("📊 资源汇总分析")
        print(f"{'='*60}")

        # 按课程分组
        courses = {}
        for resource in all_resources:
            course_id = resource["course_id"]
            if course_id not in courses:
                courses[course_id] = []
            courses[course_id].append(resource)

        # 统计信息
        total_resources = len(all_resources)
        completed_resources = len([r for r in all_resources if r["completed"]])
        incomplete_resources = total_resources - completed_resources

        print(f"📚 总资源数量: {total_resources}")
        print(f"✅ 已完成资源: {completed_resources}")
        print(f"❌ 未完成资源: {incomplete_resources}")

        # 按课程显示统计
        for course_id, resources in courses.items():
            completed = len([r for r in resources if r["completed"]])
            incomplete = len(resources) - completed
            print(f"\n🎓 课程 {course_id}:")
            print(f"   总资源: {len(resources)}")
            print(f"   已完成: {completed}")
            print(f"   未完成: {incomplete}")

            # 显示未完成的章节
            incomplete_sections = {}
            for resource in resources:
                if not resource["completed"]:
                    section_title = resource["section_title"]
                    if section_title not in incomplete_sections:
                        incomplete_sections[section_title] = []
                    incomplete_sections[section_title].append(resource)

            if incomplete_sections:
                print("   未完成章节:")
                for section_title, section_resources in incomplete_sections.items():
                    print(f"     - {section_title}: {len(section_resources)} 个资源")

        return courses

    def get_fsresourceid_from_page(self):
        """从页面中获取fsresourceid"""
        try:
            # 方法1: 从playerdata中获取
            fsresourceid_script = """
            if (typeof playerdata !== 'undefined' && playerdata.fsresourceid) {
                return playerdata.fsresourceid;
            }
            return null;
            """
            fsresourceid = self.driver.execute_script(fsresourceid_script)

            if fsresourceid:
                return fsresourceid

            # 方法2: 从URL中提取
            current_url = self.driver.current_url
            match = re.search(r"id=(\d+)", current_url)
            if match:
                return match.group(1)

            # 方法3: 从localStorage中获取
            localStorage_script = """
            var videoInfo = localStorage.getItem('video_playing_info');
            if (videoInfo) {
                var info = JSON.parse(videoInfo);
                return info.fsresourceid;
            }
            return null;
            """
            fsresourceid = self.driver.execute_script(localStorage_script)

            if fsresourceid:
                return fsresourceid

            print("❌ 无法从页面获取fsresourceid")
            return None

        except Exception as e:
            print(f"❌ 获取fsresourceid时出错: {e}")
            return None

    def get_player_progress(self):
        """获取播放器当前进度"""
        try:
            # 从页面元素中获取进度信息
            progress_script = """
            // 尝试从页面元素获取进度
            var progressElement = document.querySelector('.num-bfjd span');
            if (progressElement) {
                var progressText = progressElement.textContent || progressElement.innerText;
                // 提取数字部分
                var match = progressText.match(/(\\d+)%/);
                if (match) {
                    return parseInt(match[1]);
                }
            }
            
            // 尝试从播放器获取进度
            if (typeof player !== 'undefined' && typeof player.getCurrentTime === 'function' && typeof player.getDuration === 'function') {
                var currentTime = player.getCurrentTime();
                var duration = player.getDuration();
                if (duration > 0) {
                    return Math.floor((currentTime / duration) * 100);
                }
            }
            
            return 0;
            """

            progress = self.driver.execute_script(progress_script)
            return progress

        except Exception as e:
            print(f"❌ 获取播放器进度时出错: {e}")
            return 0

    def inject_autoplay_script(self):
        """注入自动播放脚本到当前页面"""
        autoplay_script = """
        (function() {
            // 强制播放
            player.play();
            
            // 如果播放失败，尝试点击播放按钮
            setTimeout(() => {
                if (player.getStatus() !== 'playing') {
                    console.log('🔄 尝试点击播放按钮...');
                    const playButton = document.querySelector('.prism-play-btn');
                    if (playButton) {
                        playButton.click();
                    }
                }
            }, 1000);

            // 修改提交间隔为5秒并重启定时器
            taskUpdateTime = 2 * 1000;
            if (task) {
                clearTaskInterval();
            }
            setTaskInterval();

            // 每隔1秒，增加viewTotalTime 10000（10秒）并且将当前播放时间增加20秒
            setInterval(function() {
                // 增加观看时长
                viewTotalTime += 10000;

                // 快进20秒
                var currentTime = player.getCurrentTime();
                var newTime = currentTime + 20;
                // 如果超过视频总时长，则设置为总时长
                if (newTime > videoDuration) {
                    newTime = videoDuration;
                }
                player.seek(newTime);

                console.log('已增加10秒观看时长，当前观看时长累计：', viewTotalTime, '当前播放时间：', newTime);
            }, 1000);
        })();
        """

        try:
            self.driver.execute_script(autoplay_script)
            print("✅ 自动播放脚本注入成功")
            return True
        except Exception as e:
            print(f"❌ 脚本注入失败: {e}")
            return False

    def play_resource(self, resources_data):
        """播放未完成的资源"""
        print(f"\n{'='*60}")
        print("🎬 开始自动播放未完成视频")
        print(f"{'='*60}")

        # 提取所有未完成的资源
        incomplete_resources = []
        for course_id, resources in resources_data.items():
            for resource in resources:
                if not resource["completed"]:
                    incomplete_resources.append(resource)
        print(f"📝 共找到 {len(incomplete_resources)} 个未完成视频")
        if not incomplete_resources:
            print("🎉 所有视频已完成，无需播放")
            return

        print(f"📝 发现 {len(incomplete_resources)} 个未完成视频")

        for i, resource in enumerate(incomplete_resources, 1):
            print(f"\n▶️ 播放第 {i}/{len(incomplete_resources)} 个视频")
            print(f"📚 课程: {resource['course_id']}")
            print(f"📖 章节: {resource['section_title']}")
            print(f"🔗 视频URL: {resource['url']}")

            try:
                # 访问视频播放页面
                self.driver.get(resource["url"])
                time.sleep(5)  # 等待页面加载

                # 获取当前页面的sesskey
                self.get_sesskey()
                if not self.sesskey:
                    print("❌ 无法获取sesskey，跳过此视频")
                    continue

                # 从页面中获取fsresourceid
                fsresourceid = self.get_fsresourceid_from_page()
                if not fsresourceid:
                    print("❌ 无法获取fsresourceid，跳过此视频")
                    continue

                print(f"🆔 获取到视频ID: {fsresourceid}")

                # 注入自动播放脚本
                if not self.inject_autoplay_script():
                    print("❌ 自动播放脚本注入失败，跳过此视频")
                    continue

                # 监控进度直到完成
                max_wait_time = 600  # 最大等待时间10分钟
                check_interval = 5  # 每10秒检查一次进度
                start_time = time.time()
                last_progress = 0
                stuck_count = 0

                while time.time() - start_time < max_wait_time:
                    # 获取当前进度
                    progress = self.get_player_progress()

                    if progress >= 95:
                        print(f"✅ 视频播放完成，进度: {progress}%")
                        # 更新资源状态为已完成
                        resource["completed"] = True
                        break
                    elif progress > last_progress:
                        print(f"⏳ 当前进度: {progress}%，继续播放...")
                        last_progress = progress
                        stuck_count = 0
                    else:
                        # 进度没有变化，可能是卡住了
                        stuck_count += 1
                        print(f"⚠️ 进度停滞: {progress}%，已停滞 {stuck_count} 次")

                        if stuck_count >= 3:
                            print("🔄 检测到进度停滞，尝试重新注入脚本...")
                            self.inject_autoplay_script()
                            stuck_count = 0

                    # 等待一段时间后再次检查
                    time.sleep(check_interval)
                else:
                    print("⏰ 播放超时，跳过此视频")

                # 短暂休息
                time.sleep(2)

            except Exception as e:
                print(f"❌ 播放视频时出错: {e}")
                continue

        print(f"\n🎉 所有视频播放完成！")

    def close(self):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()


if __name__ == "__main__":
    # username = "241010131550588"
    # password = "200517CHl.."
    username = "241010131550694"
    password = "az307102."
    CHROMEDRIVER_PATH = r"F:\ProjectNotes\Python\chromedriver-win64\\chromedriver.exe"

    # 课程URL列表
    course_urls = [
        "https://courses.gdut.edu.cn/course/view.php?id=2575",
        "https://courses.gdut.edu.cn/course/view.php?id=2470",
        "https://courses.gdut.edu.cn/course/view.php?id=2469",
    ]

    player = CourseAutoPlayer(CHROMEDRIVER_PATH)

    try:
        # 登录
        if player.login(username, password):
            print("\n🎉 登录成功，开始获取课程数据...")

            # 获取所有课程的资源
            all_resources = player.get_all_courses_resources(course_urls)

            # 分析课程属性
            courses_data = player.analyze_resources(all_resources)

            # 播放未完成的资源
            player.play_resource(courses_data)

        else:
            print("❌ 登录失败，无法继续")

    except Exception as e:
        print(f"❌ 程序运行出错: {e}")

    finally:
        player.close()
        print("程序结束")
