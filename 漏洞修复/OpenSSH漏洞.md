源码包：[https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-9.8p1.tar.gz](https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-9.8p1.tar.gz)

<font style="color:#DF2A3F;">前提：openssl >= 1.1.1w版本</font>

### 源码编译
```shell
# 备份配置
mv /etc/ssh{,_old_bak}

# 编译
./configure --prefix=/usr/local/openssh/ --sysconfdir=/etc/ssh/ --with-openssl-includes=/usr/local/openssl/include/ --with-ssl-dir=/usr/local/openssl/ 
make
make install

# 备份
mv /usr/sbin/sshd{,_old}
mv /usr/bin/ssh{,_old}
mv /usr/bin/ssh-add{,_old}
mv /usr/bin/ssh-agent{,_old}
mv /usr/bin/ssh-keygen{,_old}
mv /usr/bin/ssh-keyscan{,_old}

# 软连接
ln -s /usr/local/openssh/sbin/sshd /usr/sbin/sshd
ln -s /usr/local/openssh/bin/ssh /usr/bin/ssh
ln -s /usr/local/openssh/bin/ssh-add /usr/bin/ssh-add
ln -s /usr/local/openssh/bin/ssh-agent /usr/bin/ssh-agent
ln -s /usr/local/openssh/bin/ssh-keygen /usr/bin/ssh-keygen
ln -s /usr/local/openssh/bin/ssh-keyscan /usr/bin/ssh-keyscan

# 修改配置
sed -ri 's/^#PermitRootLogin/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -ri 's/^#PasswordAuthentication/PasswordAuthentication yes/' /etc/ssh/sshd_config

# 检查配置
 cat /etc/ssh/sshd_config |grep -v ^#|grep -v ^$
 
# 配置启动项
cp -r contrib/redhat/sshd.init /etc/init.d/sshd
chkconfig --add sshd
chkconfig sshd on
systemctl restart sshd

# 验证
sshd -V
```

### RPM制作
```shell
# 准备工作
mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
cp openssh-9.8p1.tar.gz ~/rpmbuild/SOURCES
```

```makefile
Name:           openssh
Version:        9.8p1
Release:        1%{?dist}
Summary:        OpenSSH compiled with custom OpenSSL

License:        BSD
URL:            https://www.openssh.com/
Source0:        openssh-9.8p1.tar.gz

BuildRequires:  gcc, make, perl, pam-devel, openssl-devel
Requires(post): initscripts, shadow-utils

%description
This package upgrades the system's OpenSSH binaries by compiling from source,
installing them to /usr/local/openssh and creating symbolic links to replace
the system versions safely.

%prep
%setup -q

%build
./configure \
    --prefix=/usr/local/openssh \
    --sysconfdir=/etc/ssh \
    --with-ssl-dir=/usr/local/openssl \
    --with-pam \
    --with-zlib \
    --with-md5-passwords
make %{?_smp_mflags} -j 4

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/usr/local/openssh
mkdir -p %{buildroot}/etc/init.d

make install DESTDIR=%{buildroot} -j 4

# Copy init script
cp contrib/redhat/sshd.init %{buildroot}/etc/init.d/sshd

%files
/usr/local/openssh/
/etc/ssh/
/etc/init.d/sshd

%post
# 备份目录
TIMESTAMP=$(date +%Y%m%d%H%M%S)
BACKUP_DIR="/usr/local/openssh-backup-$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

# 备份旧文件
for bin in sshd ssh ssh-add ssh-agent ssh-keygen ssh-keyscan; do
    if [ -f "/usr/sbin/$bin" ]; then
        cp -a "/usr/sbin/$bin" "$BACKUP_DIR/" 2>/dev/null || true
    fi
    if [ -f "/usr/bin/$bin" ]; then
        cp -a "/usr/bin/$bin" "$BACKUP_DIR/" 2>/dev/null || true
    fi
done

cp -ra /etc/ssh/ "$BACKUP_DIR/" 2>/dev/null || true

# 删除旧软链接
for bin in sshd ssh ssh-add ssh-agent ssh-keygen ssh-keyscan; do
    rm -f "/usr/sbin/$bin" "/usr/bin/$bin" 2>/dev/null || true
done

# 创建新软链接
ln -s /usr/local/openssh/sbin/sshd /usr/sbin/sshd
ln -s /usr/local/openssh/bin/ssh /usr/bin/ssh
ln -s /usr/local/openssh/bin/ssh-add /usr/bin/ssh-add
ln -s /usr/local/openssh/bin/ssh-agent /usr/bin/ssh-agent
ln -s /usr/local/openssh/bin/ssh-keygen /usr/bin/ssh-keygen
ln -s /usr/local/openssh/bin/ssh-keyscan /usr/bin/ssh-keyscan

# 修改配置
if [ -f /etc/ssh/sshd_config ]; then
    sed -i 's/^#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
    sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
fi

# 安装 init 脚本
if [ ! -f /etc/init.d/sshd ]; then
    cp -f /etc/init.d/sshd /etc/init.d/sshd
    chkconfig --add sshd
    chkconfig sshd on
fi

chmod 600 /etc/ssh/ssh_host_*_key
chown root:root /etc/ssh
chmod 755 /etc/ssh

# 重启服务
systemctl daemon-reload
systemctl restart sshd

# 打印信息
echo "OpenSSH 已安装到 /usr/local/openssh"
echo "旧版本文件和脚本备份在 $BACKUP_DIR"
echo "使用 'sshd -V' 检查版本"
```

```shell
# 制作rpm
rpmbuild -ba rpmbuild/SPECS/openssh-9.8p1.spec
```

![](https://cdn.nlark.com/yuque/0/2025/png/29476003/1749052626702-4e6d20ac-ec8c-42d1-889f-11a473352bdc.png)

