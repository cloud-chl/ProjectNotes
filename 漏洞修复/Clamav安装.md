源码包：https://github.com/Cisco-Talos/clamav/archive/refs/tags/clamav-1.4.3.zip



### 源码编译(基于CentOS7)
<font style="color:#DF2A3F;">安装前提：openssl>1.1.x，建议升级到1.1.1w or 3.0.x版本</font>

#### <font style="color:#000000;">安装依赖</font>
```shell
# 配置阿里云yum源
curl -o /etc/yum.repos.d/CentOS-Base.repo https://mirrors.aliyun.com/repo/Centos-7.repo
# 安装基础组件
yum install -y gcc gcc-c++ make python3 python3-pip valgrind git
# 安装依赖包
yum install -y bzip2-devel check-devel libcurl-devel libxml2-devel ncurses-devel openssl-devel pcre2-devel sendmail-devel zlib-devel
```

#### <font style="color:#000000;">安装 cmake</font>
<font style="color:rgb(77, 77, 77);">依赖版本：3.14+</font>

```shell
# 配置pip清华源
mkdir ~/.pip
echo '
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple/

[install]
trusted-host = pypi.tuna.tsinghua.edu.cn
' > ~/.pip/pip.conf
  
# pip安装cmake
python3 -m pip install --upgrade pip setuptools wheel scikit-build
python3 -m pip install cmake pytest

# 查看cmake版本
cmake --version
```

#### <font style="color:#000000;">安装 rust</font>
<font style="color:rgb(77, 77, 77);">依赖版本：1.56+</font>

```shell
# 安装rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh # 直接回车
source "$HOME/.cargo/env"
# 查看rust版本
rustc --version
```

#### <font style="color:#000000;">创建用户及目录文件</font>
```shell
# 创建用户和组
groupadd clamav
useradd -g clamav -s /bin/false -c "Clam Antivirus" clamav
# 创建日志存放目录和文件
mkdir -p /usr/local/clamav/logs
touch /usr/local/clamav/logs/clamd.log
touch /usr/local/clamav/logs/freshclam.log
# 创建隔离文件存放目录
mkdir -p /usr/local/clamav/infected
# 创建病毒库文件存放目录
mkdir -p /usr/local/clamav/update
# 修改目录权限
chown -R clamav.clamav /usr/local/clamav/
```

### 编译安装
```shell
# 下载源码包
wget https://github.com/Cisco-Talos/clamav/archive/refs/tags/clamav-1.4.3.zip
unzip clamav-1.4.3.zip

# 安装
cd clamav-1.4.3
mkdir build && cd build
cmake .. \
    -D CMAKE_INSTALL_PREFIX=/usr/local/clamav \
    -D CMAKE_INSTALL_LIBDIR=/usr/local/clamav/lib64 \
    -D APP_CONFIG_DIRECTORY=/usr/local/clamav/etc \
    -D DATABASE_DIRECTORY=/usr/local/clamav/lib \
    -D ENABLE_JSON_SHARED=OFF
cmake --build .
cmake --build . --target install
# 查看版本
/usr/local/clamav/bin/clamscan --version
```

**编译报错解决**

```shell
CMake Error at /opt/cmake/share/cmake-3.29/Modules/FindPackageHandleStandardArgs.cmake:230 (message):
Could NOT find Libcheck (missing: LIBCHECK_INCLUDE_DIR LIBCHECK_LIBRARY)
安装以下依赖解决
yum install check
yum install check-devel
 
CMake Error at /FindPackageHandleStandardArgs.cmake:230 (message):Could NOT find OpenSSL, try to set the path to OpenSSL root folder in the system variable OPENSSL_ROOT_DIR (missing: OPENSSL_CRYPTO_LIBRARY OPENSSL_INCLUDE_DIR)
安装以下依赖解决
yum install openssl-devel 
 
CMake Error at /opt/cmake/share/cmake-3.29/Modules/FindPackageHandleStandardArgs.cmake:230 (message):
Could NOT find BZip2 (missing: BZIP2_LIBRARIES BZIP2_INCLUDE_DIR)
安装以下依赖解决
yum install bzip2-devel
 
CMake Error at /opt/cmake/share/cmake-3.29/Modules/FindPackageHandleStandardArgs.cmake:230 (message):
Could NOT find LibXml2 (missing: LIBXML2_LIBRARY LIBXML2_INCLUDE_DIR)
安装以下依赖解决
yum install libxml2-devel
 
CMake Error at /opt/cmake/share/cmake-3.29/Modules/FindPackageHandleStandardArgs.cmake:230 (message):
Could NOT find PCRE2 (missing: PCRE2_LIBRARIES PCRE2_INCLUDE_DIR)
安装以下依赖解决
yum install pcre2-devel
 
Make Error at /opt/cmake/share/cmake-3.29/Modules/FindPackageHandleStandardArgs.cmake:230 (message):
Could NOT find JSONC (missing: JSONC_LIBRARIES JSONC_INCLUDE_DIRS)
安装以下依赖解决
yum install json-c-devel.x86_64 
 
Make Error at /opt/cmake/share/cmake-3.29/Modules/FindPackageHandleStandardArgs.cmake:230 (message):
Could NOT find CURL (missing: CURL_LIBRARY CURL_INCLUDE_DIR)
安装以下依赖解决
yum install curl-devel
 
CMake Error at cmake/FindCURSES.cmake:143 (message):
Unable to find ncurses or pdcurses
安装以下依赖解决
yum install ncurses-devel
 
CMake Error at /opt/cmake/share/cmake-3.29/Modules/FindPackageHandleStandardArgs.cmake:230 (message):
Could NOT find Milter (missing: Milter_LIBRARY Milter_INCLUDE_DIR)
安装以下依赖解决
yum install sendmail-devel
```

#### 修改配置文件
```shell
# 复制配置文件
cp /etc/clamav/clamd.conf.sample /etc/clamav/clamd.conf
cp /etc/clamav/freshclam.conf.sample /etc/clamav/freshclam.conf

# 注释掉Example行
sed -i 's/Example/#Example/g' /etc/clamav/clamd.conf
# 文末追加配置
echo -e '
User clamav
TCPSocket 3310
LogFile /usr/local/clamav/logs/clamd.log
PidFile /usr/local/clamav/update/clamd.pid  
DatabaseDirectory /usr/local/clamav/update
' >> /etc/clamav/clamd.conf

# 注释掉Example行
sed -i 's/Example/#Example/g' /etc/clamav/freshclam.conf
# 文末追加配置
echo -e '
DatabaseDirectory /usr/local/clamav/update
UpdateLogFile /usr/local/clamav/logs/freshclam.log
PidFile /usr/local/clamav/update/freshclam.pid
' >> /etc/clamav/freshclam.conf
```

#### 更新病毒库
```shell
# 手动执行更新
/usr/local/clamav/bin/freshclam
# 显示当前病毒库的版本
/usr/local/clamav/bin/freshclam -V
```

#### 启动clamd
```shell
#!/bin/bash

CLAMAV_HOME=/usr/local/clamav
nohup $CLAMAV_HOME/sbin/clamd --foreground=true --config-file=$CLAMAV_HOME/etc/clamd.conf &
```

