源码包：[https://github.com/openssl/openssl/releases/download/OpenSSL_1_1_1w/openssl-1.1.1w.tar.gz](https://github.com/openssl/openssl/releases/download/OpenSSL_1_1_1w/openssl-1.1.1w.tar.gz)

### 源码编译
```shell
yum install wget openssl-devel zlib-devel pam-devel libX11-devel gtk3-devel libnotify-devel libXtst-devel -y

yum groupinstall "Development Tools" -y
```

```shell
# 编译
./config --prefix=/usr/local/openssl shared -fPIC
make && make install

# 检查库文件是否正常
ldd /usr/local/openssl/bin/openssl  # 检查函数库
export OPENSSL_ROOT_DIR=/usr/local/openssl
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$OPENSSL_ROOT_DIR/lib
/usr/sbin/ldconfig -v  # 更新函数库

# 备份
OPENSSL_ROOT_PATH=/usr/local/openssl
OPENSSL_PATH=/usr/bin/openssl
mv $OPENSSL_PATH $OPENSSL_PATH_`date +%Y-%m-%d_%H:%M:%S`

# 软链接到新目录
ln -sv $OPENSSL_ROOT_PATH/bin/openssl $OPENSSL_PATH
ln -sv $OPENSSL_ROOT_PATH/lib/libssl.so.1.1 /usr/lib64/libssl.so.1.1
ln -sv $OPENSSL_ROOT_PATH/lib/libcrypto.so.1.1 /usr/lib64/libcrypto.so.1.1

# 增加openssl库路径
echo "/usr/local/openssl/lib/" >> /etc/ld.so.conf

# 刷新
ldconfig -v
```



### RPM制作
```shell
# 准备工作
mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
cp openssl-1.1.1w.tar.gz ~/rpmbuild/SOURCES

# 版本回退
# 查看备份目录
ls /usr/local/openssl-backup-*

# 假设你的备份目录是 /usr/local/openssl-backup-20250604120000
cd /usr/local/openssl-backup-20250604120000

# 恢复文件
cp -a openssl /usr/bin/
cp -a libssl.so.1.1 /usr/lib64/
cp -a libcrypto.so.1.1 /usr/lib64/

# 删除软链接
rm -f /usr/bin/openssl /usr/lib64/libssl.so.1.1 /usr/lib64/libcrypto.so.1.1

# 重新链接回旧版
ln -s /usr/bin/openssl /usr/bin/openssl
ln -s /usr/lib64/libssl.so.1.1 /usr/lib64/libssl.so.1.1
ln -s /usr/lib64/libcrypto.so.1.1 /usr/lib64/libcrypto.so.1.1

# 刷新动态库缓存
ldconfig
```

```makefile
Name:           openssl
Version:        1.1.1w
Release:        %{?dist}
Summary:        OpenSSL Toolkit

License:        OpenSSL
URL:            https://www.openssl.org
Source0:        openssl-1.1.1w.tar.gz

BuildRequires:  gcc, make, perl

%description
OpenSSL is a collaborative project to develop a robust, commercial-grade,
fully featured, and Open Source toolkit implementing the Secure Sockets Layer
(SSL v2/v3) and Transport Layer Security (TLS v1) protocols as well as a full-strength general-purpose cryptography library.

%prep
%setup -q

%build
./config --prefix=/usr/local/openssl shared -fPIC
make %{?_smp_mflags} -j 4

%install
rm -rf %{buildroot}
make install DESTDIR=%{buildroot} -j 4

# 创建 ld.so.conf.d 配置文件
mkdir -p %{buildroot}/etc/ld.so.conf.d
echo "/usr/local/openssl/lib" > %{buildroot}/etc/ld.so.conf.d/openssl.conf

%files
/usr/local/openssl/
/etc/ld.so.conf.d/openssl.conf

%post
# 获取当前时间戳用于备份目录名
TIMESTAMP=$(date +%Y%m%d%H%M%S)
BACKUP_DIR="/usr/local/openssl-backup-$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

# 仅备份文件（不处理软链接）
for file in /usr/bin/openssl /usr/lib64/libssl.so.1.1 /usr/lib64/libcrypto.so.1.1; do
  # 检查是否是真实文件（排除软链接）
  if [ -f "$file" -a ! -L "$file" ]; then
    mv -v "$file" "$BACKUP_DIR/" || echo "备份 $file 失败"
  fi
done

%posttrans 
# 创建新的软链接
ln -sfv /usr/local/openssl/lib/libssl.so.1.1 /usr/lib64/libssl.so.1.1
ln -sfv /usr/local/openssl/lib/libcrypto.so.1.1 /usr/lib64/libcrypto.so.1.1
ln -sfv /usr/local/openssl/bin/openssl /usr/bin/openssl

# 更新动态链接缓存
/sbin/ldconfig

# 打印信息
echo "OpenSSL 已安装到 /usr/local/openssl"
echo "旧版本文件和脚本备份在 $BACKUP_DIR"
echo "使用 'openssl version' 检查版本"
```

```shell
# 制作rpm
rpmbuild -ba rpmbuild/SPECS/openssl-1.1.1w.spec
```

![](https://cdn.nlark.com/yuque/0/2025/png/29476003/1749051214224-3733f168-cd77-4328-9c85-8abd635bb172.png)

