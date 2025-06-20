<h2 id="Jnjti">一、环境准备</h2>
| **<font style="color:rgb(79, 79, 79);">操作系统</font>** | **内核版本** | **<font style="color:rgb(79, 79, 79);">IP地址</font>** |  **<font style="color:rgb(79, 79, 79);">角色</font>**  | **<font style="color:rgb(79, 79, 79);">硬盘</font>** | **<font style="color:rgb(79, 79, 79);">CPU & MEM</font>** |
| :------------------------------------------------------: | ------------ | ------------------------------------------------------ | :----------------------------------------------------: | :--------------------------------------------------: | :-------------------------------------------------------: |
|   <font style="color:rgb(79, 79, 79);">Centos 8</font>   | 5.4+         | 192.168.124.21                                         | <font style="color:rgb(79, 79, 79);">k8s-master</font> |   <font style="color:rgb(79, 79, 79);">50GB</font>   |     <font style="color:rgb(79, 79, 79);">2核4G</font>     |
|   <font style="color:rgb(79, 79, 79);">Centos 8</font>   | 5.4+         | 192.168.124.22                                         | <font style="color:rgb(79, 79, 79);">k8s-node1</font>  |   <font style="color:rgb(79, 79, 79);">50GB</font>   |    <font style="color:rgb(79, 79, 79);">4核10G</font>     |
|   <font style="color:rgb(79, 79, 79);">Centos 8</font>   | 5.4+         | 192.168.124.23                                         | <font style="color:rgb(79, 79, 79);">k8s-node2</font>  |   <font style="color:rgb(79, 79, 79);">50GB</font>   |    <font style="color:rgb(79, 79, 79);">4核10G</font>     |

<h2 id="Tsgzr"><font style="color:rgb(79, 79, 79);">二、系统初始化</font></h2>
<h3 id="WNKcJ">2.1 关闭防火墙</h3>
```bash
systemctl stop firewalld
systemctl disable firewalld
```

<h3 id="E3VVh">2.2 关闭SELINUX</h3>
```bash
setenforce 0
sed -ri 's/SELINUX=enforcing/SELINUX=disabled/g' /etc/selinux/config
```

<h3 id="Nb2li">2.3 关闭swap分区</h3>
```bash
swapoff -a
sed -ri 's/.*swap.*/#&/' /etc/fstab
```

<h3 id="nPdB9">2.4 规划主机名</h3>

```bash
hostnamectl set-hostname k8s-master
hostnamectl set-hostname k8s-nod1
hostnamectl set-hostname k8s-nod2
```

<h3 id="bbc8H">2.5 配置hosts解析</h3>
```bash
cat >>/etc/hosts<<-EOF
192.168.124.21 k8s-master
192.168.124.22 k8s-node1
192.168.124.23 k8s-node2
EOF
```

<h3 id="UPlox">2.6 配置yum源</h3>
```bash
# BaseRepo
curl -o /etc/yum.repos.d/CentOS-Base.repo https://mirrors.aliyun.com/repo/Centos-vault-8.5.2111.repo

# Epel

yum install -y https://mirrors.aliyun.com/epel/epel-release-latest-8.noarch.rpm
sed -i 's|^#baseurl=https://download.example/pub|baseurl=https://mirrors.aliyun.com|' /etc/yum.repos.d/epel*
sed -i 's|^metalink|#metalink|' /etc/yum.repos.d/epel*

````

<h3 id="i3ujJ">2.7 常用工具</h3>
```bash
yum -y install wget jq psmisc vim net-tools nfs-utils telnet yum-utils device-mapper-persistent-data lvm2 git network-scripts tar curl -y
````

<h3 id="nB2fV">2.8 二进制包下载</h3>
```bash
# Kubernetes
https://storage.googleapis.com/kubernetes-release/release/v1.24.2/kubernetes-server-linux-amd64.tar.gz

# cfssl

https://github.com/cloudflare/cfssl/releases/download/v1.6.1/cfssl_1.6.1_linux_amd64
https://github.com/cloudflare/cfssl/releases/download/v1.6.1/cfssljson_1.6.1_linux_amd64
https://github.com/cloudflare/cfssl/releases/download/v1.6.1/cfssl-certinfo_1.6.1_linux_amd64

# Etcd

https://github.com/etcd-io/etcd/releases/download/v3.5.4/etcd-v3.5.4-linux-amd64.tar.gz

# Containerd

https://github.com/containerd/containerd/releases/download/v1.6.8/cri-containerd-cni-1.6.8-linux-amd64.tar.gz

# crictl 客户端

https://github.com/kubernetes-sigs/cri-tools/releases/download/v1.24.2/crictl-v1.24.2-linux-amd64.tar.gz

# CNI 插件

https://github.com/containernetworking/plugins/releases/download/v1.1.1/cni-plugins-linux-amd64-v1.1.1.tgz

````

<h3 id="tuWU7">2.9 网络配置</h3>
```bash
# 方式一
systemctl disable --now NetworkManager
systemctl start network && systemctl enable network

# 方式二
cat > /etc/NetworkManager/conf.d/calico.conf << EOF
[keyfile]
unmanaged-devices=interface-name:cali*;interface-name:tunl*
EOF
systemctl restart NetworkManager
````

<h3 id="VYFmX">2.10 时间同步 </h3>
```bash
# 使用阿里的时间服务器
yum install chrony -y
cat > /etc/chrony.conf << EOF 
pool ntp.aliyun.com iburst
driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
keyfile /etc/chrony.keys
leapsectz right/UTC
logdir /var/log/chrony
EOF

systemctl start chronyd && systemctl enabel chronyd

# 使用客户端进行验证

chronyc sources -v

````

<h3 id="eKzIX"><font style="color:rgb(79, 79, 79);">2.11 配置ulimit</font></h3>
```bash
ulimit -SHn 65535
cat >> /etc/security/limits.conf <<EOF
* soft nofile 655360
* hard nofile 131072
* soft nproc 655350
* hard nproc 655350
* seft memlock unlimited
* hard memlock unlimitedd
EOF
````

<h3 id="qnGkW">2.12 配置免密登录</h3>
```bash
yum install -y sshpass
ssh-keygen -f /root/.ssh/id_rsa -P ''
export IP="192.168.124.21 192.168.124.22 192.168.124.23"
export SSHPASS=qwe
for HOST in $IP;do
     sshpass -e ssh-copy-id -o StrictHostKeyChecking=no $HOST
done
```

<h3 id="ZNwjx">2.13 安装ipvsadm</h3>
```bash
yum install ipvsadm ipset sysstat conntrack libseccomp -y
cat > /etc/modules-load.d/ipvs.conf <<EOF 
ip_vs
ip_vs_rr
ip_vs_wrr
ip_vs_sh
nf_conntrack
ip_tables
ip_set
xt_set
ipt_set
ipt_rpfilter
ipt_REJECT
ipip
EOF
 
systemctl restart systemd-modules-load.service
 
lsmod | grep -e ip_vs -e nf_conntrack
ip_vs_sh               16384  0
ip_vs_wrr              16384  0
ip_vs_rr               16384  0
ip_vs                 180224  6 ip_vs_rr,ip_vs_sh,ip_vs_wrr
nf_conntrack          176128  1 ip_vs
libcrc32c              16384  3 nf_conntrack,xfs,ip_vs
```

<h3 id="bLJQO">2.14 修改内核参数</h3>
```bash
cat <<EOF > /etc/sysctl.d/k8s.conf
net.ipv4.ip_forward = 1
net.bridge.bridge-nf-call-iptables = 1
fs.may_detach_mounts = 1
vm.overcommit_memory=1
vm.panic_on_oom=0
fs.inotify.max_user_watches=89100
fs.file-max=52706963
fs.nr_open=52706963
net.netfilter.nf_conntrack_max=2310720
 
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_probes = 3
net.ipv4.tcp_keepalive_intvl =15
net.ipv4.tcp_max_tw_buckets = 36000
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_max_orphans = 327680
net.ipv4.tcp_orphan_retries = 3
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 16384
net.ipv4.ip_conntrack_max = 65536
net.ipv4.tcp_max_syn_backlog = 16384
net.ipv4.tcp_timestamps = 0
net.core.somaxconn = 16384
 
net.ipv6.conf.all.disable_ipv6 = 0
net.ipv6.conf.default.disable_ipv6 = 0
net.ipv6.conf.lo.disable_ipv6 = 0
net.ipv6.conf.all.forwarding = 1
EOF
 
sysctl --system
```

<h2 id="Qa0be">三、Kubernetes基本组件安装</h2>
<h3 id="v3svg">3.1 Containerd</h3>
<h4 id="zQeBK">3.1.1 Containerd安装配置</h4>
```bash
# wget https://github.com/containernetworking/plugins/releases/download/v1.1.1/cni-plugins-linux-amd64-v1.1.1.tgz
#创建cni插件所需目录
mkdir -p /etc/cni/net.d /opt/cni/bin 
#解压cni二进制包
tar xf cni-plugins-linux-amd64-v1.1.1.tgz -C /opt/cni/bin/
 
# wget https://github.com/containerd/containerd/releases/download/v1.6.6/cri-containerd-cni-1.6.6-linux-amd64.tar.gz
#解压
tar -xzf cri-containerd-cni-1.6.8-linux-amd64.tar.gz -C /
 
#创建服务启动文件
cat > /etc/systemd/system/containerd.service <<EOF
[Unit]
Description=containerd container runtime
Documentation=https://containerd.io
After=network.target local-fs.target
 
[Service]
ExecStartPre=-/sbin/modprobe overlay
ExecStart=/usr/local/bin/containerd
Type=notify
Delegate=yes
KillMode=process
Restart=always
RestartSec=5
LimitNPROC=infinity
LimitCORE=infinity
LimitNOFILE=infinity
TasksMax=infinity
OOMScoreAdjust=-999
 
[Install]
WantedBy=multi-user.target
EOF
```

<h4 id="hEpqz"><font style="color:rgb(79, 79, 79);">3.1.2 配置Containerd所需的模块</font></h4>
```bash
cat <<EOF | sudo tee /etc/modules-load.d/containerd.conf
overlay
br_netfilter
EOF

# 加载模块

systemctl restart systemd-modules-load.service

````

<h4 id="V7Ovc"><font style="color:rgb(79, 79, 79);">3.1.3 配置Containerd所需的内核</font></h4>
```bash
cat <<EOF | sudo tee /etc/sysctl.d/99-kubernetes-cri.conf
net.bridge.bridge-nf-call-iptables  = 1
net.ipv4.ip_forward                 = 1
net.bridge.bridge-nf-call-ip6tables = 1
EOF

# 加载内核
sysctl --system
````

<h4 id="nqHem"><font style="color:rgb(79, 79, 79);">3.1.4 创建Containerd的配置文件</font></h4>
```bash
# 创建默认配置文件
mkdir -p /etc/containerd
containerd config default | tee /etc/containerd/config.toml
 
# 修改Containerd的配置文件
sed -i "s#SystemdCgroup\ \=\ false#SystemdCgroup\ \=\ true#g" /etc/containerd/config.toml
cat /etc/containerd/config.toml | grep SystemdCgroup
 
sed -i "s#k8s.gcr.io#registry.cn-hangzhou.aliyuncs.com/chenby#g" /etc/containerd/config.toml
cat /etc/containerd/config.toml | grep sandbox_image
```

<h4 id="OjMbG"><font style="color:rgb(79, 79, 79);">3.1.5 启动并设置为开机启动</font></h4>
```bash
systemctl daemon-reload
systemctl enable --now containerd
```

<h4 id="eH5p5"><font style="color:rgb(79, 79, 79);">3.1.6 配置crictl客户端连接的运行位置</font></h4>
```bash
# wget https://github.com/kubernetes-sigs/cri-tools/releases/download/v1.24.2/crictl-v1.24.2-linux-amd64.tar.gz
 
# 解压
tar xf crictl-v1.24.2-linux-amd64.tar.gz -C /usr/bin/
# 生成配置文件
cat > /etc/crictl.yaml <<EOF
runtime-endpoint: unix:///run/containerd/containerd.sock
image-endpoint: unix:///run/containerd/containerd.sock
timeout: 10
debug: false
EOF
 
# 测试
systemctl restart  containerd
crictl info
```

<h3 id="UtkR6">3.2 Etcd</h3>
<h4 id="dgEQ8">3.2.1 安装包和工具</h4>
```bash
wget https://github.com/cloudflare/cfssl/releases/download/v1.6.1/cfssl_1.6.1_linux_amd64
wget https://github.com/cloudflare/cfssl/releases/download/v1.6.1/cfssljson_1.6.1_linux_amd64
wget https://github.com/cloudflare/cfssl/releases/download/v1.6.1/cfssl-certinfo_1.6.1_linux_amd64

chmod +x cfssl_1.6.1_linux_amd64 cfssljson_1.6.1_linux_amd64 cfssl-certinfo_1.6.1_linux_amd64

mv cfssl_1.6.1_linux_amd64 /usr/bin/cfssl
mv cfssljson_1.6.1_linux_amd64 /usr/bin/cfssljson
mv cfssl-certinfo_1.6.1_linux_amd64 /usr/bin/cfssl-certinfo

````

```bash
wget https://github.com/etcd-io/etcd/releases/download/v3.5.4/etcd-v3.5.4-linux-amd64.tar.gz

mkdir -p /opt/etcd/{ssl,bin,cfg}

tar -xvf etcd*.tar.gz && mv etcd-*/etcd /opt/etcd/bin/ && mv etcd-*/etcdctl /opt/etcd/bin/
````

<h4 id="DsOZk">3.2.2 签发Etcd证书</h4>
```json
mkdir ~/TLS/{etcd,k8s} -p
cd ~/TLS/etcd

cat > ca-config.json << EOF
{
"signing": {
"default": {
"expiry": "87600h"
},
"profiles": {
"www": {
"expiry": "87600h",
"usages": [
"signing",
"key encipherment",
"server auth",
"client auth"
]
}
}
}
}
EOF

cat > ca-csr.json << EOF
{
"CN": "etcd CA",
"key": {
"algo": "rsa",
"size": 2048
},
"names": [
{
"C": "CN",
"L": "Beijing",
"ST": "Beijing"
}
]
}
EOF

# 生成证书：

cfssl gencert -initca ca-csr.json | cfssljson -bare ca -

````

```json
cat > server-csr.json << EOF
{
    "CN": "etcd",
    "hosts": [
    "192.168.124.21",
    "192.168.124.31",
    "192.168.124.41"
    ],
    "key": {
        "algo": "rsa",
        "size": 2048
    },
    "names": [
        {
            "C": "CN",
            "L": "BeiJing",
            "ST": "BeiJing"
        }
    ]
}
EOF

# 生成证书
cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json -profile=www server-csr.json | cfssljson -bare server

# 复制证书到etcd目录下
cp ~/TLS/etcd/ca*pem ~/TLS/etcd/server*pem /opt/etcd/ssl/
````

<h4 id="aDeSR">3.2.3 Etcd配置文件和启动配置</h4>
```nginx
cat > /opt/etcd/cfg/etcd.conf << EOF
#[Member]
ETCD_NAME="etcd-1"
ETCD_DATA_DIR="/var/lib/etcd/default.etcd"
ETCD_LISTEN_PEER_URLS="https://192.168.124.21:2380"
ETCD_LISTEN_CLIENT_URLS="https://192.168.124.21:2379"
#[Clustering]
ETCD_INITIAL_ADVERTISE_PEER_URLS="https://192.168.124.21:2380"
ETCD_ADVERTISE_CLIENT_URLS="https://192.168.124.21:2379"
ETCD_INITIAL_CLUSTER="etcd-1=https://192.168.124.21:2380"
ETCD_INITIAL_CLUSTER_TOKEN="etcd-cluster"
ETCD_INITIAL_CLUSTER_STATE="new"
EOF
```

```bash
cat > /usr/lib/systemd/system/etcd.service << EOF
[Unit]
Description=Etcd Server
After=network.target
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
EnvironmentFile=/opt/etcd/cfg/etcd.conf
ExecStart=/opt/etcd/bin/etcd \
--cert-file=/opt/etcd/ssl/server.pem \
--key-file=/opt/etcd/ssl/server-key.pem \
--peer-cert-file=/opt/etcd/ssl/server.pem \
--peer-key-file=/opt/etcd/ssl/server-key.pem \
--trusted-ca-file=/opt/etcd/ssl/ca.pem \
--peer-trusted-ca-file=/opt/etcd/ssl/ca.pem \
--logger=zap
Restart=on-failure
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# 启动etcd:
systemctl daemon-reload
systemctl restart etcd
systemctl enable etcd
systemctl status etcd
```

<h4 id="NTEAT">3.2.4 验证</h4>
```bash
# 验证Etcd集群
ETCDCTL_API=3 /opt/etcd/bin/etcdctl --cacert=/opt/etcd/ssl/ca.pem --cert=/opt/etcd/ssl/server.pem --key=/opt/etcd/ssl/server-key.pem --endpoints="https://192.168.124.21:2379" endpoint health --write-out=table
```

![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667311008679-9befdae3-4af4-4167-8c97-96336eecaead.png)

<h3 id="KqNk6">3.3 Kube-Apiserver</h3>
<h4 id="OympI">3.3.1 安装包</h4>
```bash
wget https://dl.k8s.io/v1.24.2/kubernetes-server-linux-amd64.tar.gz

# 解压 k8s 安装文件

mkdir -p /opt/kubernetes/{bin,cfg,ssl,logs}
tar -xvf kubernetes-server-linux-amd64.tar.gz --strip-components=3 -C /opt/kubernetes/bin kubernetes/server/bin/kube{let,ctl,-apiserver,-controller-manager,-scheduler,-proxy}
cp /opt/kubernetes/bin/kube{let,ctl,-proxy} /usr/local/bin

````

<h4 id="vNbuf">3.3.2 签发Apiserver证书</h4>
```bash
cd ~/TLS/k8s

cat > ca-config.json << EOF
{
  "signing": {
    "default": {
      "expiry": "87600h"
    },
    "profiles": {
      "kubernetes": {
         "expiry": "87600h",
         "usages": [
            "signing",
            "key encipherment",
            "server auth",
            "client auth"
        ]
      }
    }
  }
}
EOF
cat > ca-csr.json << EOF
{
    "CN": "kubernetes",
    "key": {
        "algo": "rsa",
        "size": 2048
    },
    "names": [
        {
            "C": "CN",
            "L": "Beijing",
            "ST": "Beijing",
            "O": "k8s",
            "OU": "System"
        }
    ]
}
EOF

# 生成证书：
cfssl gencert -initca ca-csr.json | cfssljson -bare ca -
````

```bash
cat > server-csr.json << EOF
{
    "CN": "kubernetes",
    "hosts": [
      "10.2.0.1",
      "127.0.0.1",
      "192.168.124.21",
      "192.168.124.31",
      "192.168.124.41",
      "kubernetes",
      "kubernetes.default",
      "kubernetes.default.svc",
      "kubernetes.default.svc.cluster",
      "kubernetes.default.svc.cluster.local"
    ],
    "key": {
        "algo": "rsa",
        "size": 2048
    },
    "names": [
        {
            "C": "CN",
            "L": "BeiJing",
            "ST": "BeiJing",
            "O": "k8s",
            "OU": "System"
        }
    ]
}
EOF

注：上述文件hosts字段中IP为所有Master/LB/VIP IP，一个都不能少！为了方便后期扩容可以多写几个预留的IP。

cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json -profile=kubernetes server-csr.json | cfssljson -bare server

# 将生成的pem证书到k8s目录下
cp ~/TLS/k8s/ca*pem ~/TLS/k8s/server*pem /opt/kubernetes/ssl/
```

```yaml
# 启用 TLS Bootstrapping 机制
TLS Bootstraping：Master apiserver启用TLS认证后，Node节点kubelet和kube-proxy要与kube-apiserver进行通信，必须使用CA签发的有效证书才可以，当Node节点很多时，这种客户端证书颁发需要大量工作，同样也会增加集群扩展复杂度。为了简化流程，Kubernetes引入了TLS bootstraping机制来自动颁发客户端证书，kubelet会以一个低权限用户自动向apiserver申请证书，kubelet的证书由apiserver动态签署。所以强烈建议在Node上使用这种方式，目前主要用于kubelet，kube-proxy还是由我们统一颁发一个证书。
```

![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667311976684-3fbd7553-31cf-4e15-8b01-2710db3d8cf2.png)

<h4 id="VqLu5">3.3.3 创建token</h4>
```bash
# 创建上述配置文件中token文件：
cat > /opt/kubernetes/cfg/token.csv << EOF
c47ffb939f5ca36231d9e3121a252940,kubelet-bootstrap,10001,"system:node-bootstrapper"
EOF
格式：token，用户名，UID，用户组
token也可自行生成替换：
head -c 16 /dev/urandom | od -An -t x | tr -d ' '
```

<h4 id="HWKlV">3.3.4 Apiserver配置文件</h4>
```bash
cat > /opt/kubernetes/cfg/kube-apiserver.conf << EOF
KUBE_APISERVER_OPTS="--logtostderr=false \\
--v=2 \\
--log-dir=/opt/kubernetes/logs \\
--etcd-servers=https://192.168.124.21:2379 \\
--bind-address=192.168.124.21 \\
--secure-port=6443 \\
--advertise-address=192.168.124.21 \\
--allow-privileged=true \\
--service-cluster-ip-range=10.2.0.0/16 \\
--enable-admission-plugins=NodeRestriction \\
--authorization-mode=RBAC,Node \\
--enable-bootstrap-token-auth=true \\
--token-auth-file=/opt/kubernetes/cfg/token.csv \\
--service-node-port-range=30000-32767 \\
--kubelet-client-certificate=/opt/kubernetes/ssl/server.pem \\
--kubelet-client-key=/opt/kubernetes/ssl/server-key.pem \\
--tls-cert-file=/opt/kubernetes/ssl/server.pem  \\
--tls-private-key-file=/opt/kubernetes/ssl/server-key.pem \\
--client-ca-file=/opt/kubernetes/ssl/ca.pem \\
--service-account-key-file=/opt/kubernetes/ssl/ca-key.pem \\
--service-account-issuer=api \\
--service-account-signing-key-file=/opt/kubernetes/ssl/ca-key.pem \\
--etcd-cafile=/opt/etcd/ssl/ca.pem \\
--etcd-certfile=/opt/etcd/ssl/server.pem \\
--etcd-keyfile=/opt/etcd/ssl/server-key.pem \\
--requestheader-client-ca-file=/opt/kubernetes/ssl/ca.pem \\
--proxy-client-cert-file=/opt/kubernetes/ssl/server.pem \\
--proxy-client-key-file=/opt/kubernetes/ssl/server-key.pem \\
--requestheader-allowed-names=kubernetes \\
--requestheader-extra-headers-prefix=X-Remote-Extra- \\
--requestheader-group-headers=X-Remote-Group \\
--requestheader-username-headers=X-Remote-User \\
--enable-aggregator-routing=true \\
--audit-log-maxage=30 \\
--audit-log-maxbackup=3 \\
--audit-log-maxsize=100 \\
--audit-log-path=/opt/kubernetes/logs/k8s-audit.log"
EOF
```

```bash
注：上面两个\ \ 第一个是转义符，第二个是换行符，使用转义符是为了使用EOF保留换行符。
• --logtostderr：启用日志
• ---v：日志等级
• --log-dir：日志目录
• --etcd-servers：etcd集群地址
• --bind-address：监听地址
• --secure-port：https安全端口
• --advertise-address：集群通告地址
• --allow-privileged：启用授权
• --service-cluster-ip-range：Service虚拟IP地址段
• --enable-admission-plugins：准入控制模块
• --authorization-mode：认证授权，启用RBAC授权和节点自管理
• --enable-bootstrap-token-auth：启用TLS bootstrap机制
• --token-auth-file：bootstrap token文件
• --service-node-port-range：Service nodeport类型默认分配端口范围
• --kubelet-client-xxx：apiserver访问kubelet客户端证书
• --tls-xxx-file：apiserver https证书
• 1.20版本必须加的参数：--service-account-issuer，--service-account-signing-key-file
• --etcd-xxxfile：连接Etcd集群证书
• --audit-log-xxx：审计日志
• 启动聚合层相关配置：--requestheader-client-ca-file，--proxy-client-cert-file，--proxy-client-key-file，--requestheader-allowed-names，--requestheader-extra-headers-prefix，--requestheader-group-headers，--requestheader-username-headers，--enable-aggregator-routing
```

<h4 id="iDDGD">3.3.5 systemd管理Apiserver</h4>
```bash
cat > /etc/systemd/system/kube-apiserver.service << EOF
[Unit]
Description=Kubernetes API Server
Documentation=https://github.com/kubernetes/kubernetes

[Service]
EnvironmentFile=/opt/kubernetes/cfg/kube-apiserver.conf
ExecStart=/opt/kubernetes/bin/kube-apiserver \$KUBE_APISERVER_OPTS
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# 启动并设置开机启动

systemctl daemon-reload
systemctl restart kube-apiserver
systemctl enable kube-apiserver
systemctl status kube-apiserver

````

![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667312203092-b8876c05-dd11-4b77-8311-81c1c263716b.png)

<h3 id="YIAad">3.4 Kube-Controller-Manager</h3>
<h4 id="Bitka">3.4.1 签发Controller-Manager证书</h4>
```json
cd ~/TLS/k8s

cat > kube-controller-manager-csr.json << EOF
{
  "CN": "system:kube-controller-manager",
  "hosts": [],
  "key": {
    "algo": "rsa",
    "size": 2048
  },
  "names": [
    {
      "C": "CN",
      "L": "BeiJing",
      "ST": "BeiJing",
      "O": "system:masters",
      "OU": "System"
    }
  ]
}
EOF

# 生成证书
cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json -profile=kubernetes kube-controller-manager-csr.json | cfssljson -bare kube-controller-manager
````

<h4 id="HIpJ0">3.4.2 生成Kubeconfig文件</h4>
```bash
KUBE_CONFIG="/opt/kubernetes/cfg/kube-controller-manager.kubeconfig"
KUBE_APISERVER="https://192.168.124.21:6443"

kubectl config set-cluster kubernetes \
 --certificate-authority=/opt/kubernetes/ssl/ca.pem \
 --embed-certs=true \
 --server=${KUBE_APISERVER} \
  --kubeconfig=${KUBE_CONFIG}

kubectl config set-credentials kube-controller-manager \
 --client-certificate=./kube-controller-manager.pem \
 --client-key=./kube-controller-manager-key.pem \
 --embed-certs=true \
 --kubeconfig=${KUBE_CONFIG}

kubectl config set-context default \
 --cluster=kubernetes \
 --user=kube-controller-manager \
 --kubeconfig=${KUBE_CONFIG}

kubectl config use-context default --kubeconfig=${KUBE_CONFIG}

````

![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667393115923-2f4a54d7-a805-47d8-8ecd-f6a93ba37d75.png)

<h4 id="LYRwy">3.4.3 Controller-Manager配置文件</h4>
```bash
cat > /opt/kubernetes/cfg/kube-controller-manager.conf << EOF
KUBE_CONTROLLER_MANAGER_OPTS="--logtostderr=false \\
--v=2 \\
--log-dir=/opt/kubernetes/logs \\
--leader-elect=true \\
--kubeconfig=/opt/kubernetes/cfg/kube-controller-manager.kubeconfig \\
--bind-address=127.0.0.1 \\
--allocate-node-cidrs=true \\
--cluster-cidr=10.1.0.0/16 \\
--service-cluster-ip-range=10.2.0.0/16 \\
--cluster-signing-cert-file=/opt/kubernetes/ssl/ca.pem \\
--cluster-signing-key-file=/opt/kubernetes/ssl/ca-key.pem  \\
--root-ca-file=/opt/kubernetes/ssl/ca.pem \\
--service-account-private-key-file=/opt/kubernetes/ssl/ca-key.pem \\
--cluster-signing-duration=87600h0m0s"
EOF
````

```bash
•--kubeconfig：连接apiserver配置文件
•--leader-elect：当该组件启动多个时，自动选举（HA）
•--cluster-signing-cert-file/--cluster-signing-key-file：自动为kubelet颁发证书的CA，与apiserver保持一致
```

<h4 id="oYBDH">3.4.4 systemd管理Kube-Controller-Manager</h4>
```bash
cat > /etc/systemd/system/kube-controller-manager.service << EOF
[Unit]
Description=Kubernetes Controller Manager
Documentation=https://github.com/kubernetes/kubernetes

[Service]
EnvironmentFile=/opt/kubernetes/cfg/kube-controller-manager.conf
ExecStart=/opt/kubernetes/bin/kube-controller-manager \$KUBE_CONTROLLER_MANAGER_OPTS
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# 启动并设置开机启动

systemctl daemon-reload
systemctl restart kube-controller-manager
systemctl enable kube-controller-manager
systemctl status kube-controller-manager

````

![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667393400966-78d936bf-c922-4836-9cd7-f26ba697e192.png)

<h3 id="S9Ymt">3.5 Kube-Scheduler</h3>
<h4 id="TDcwO">3.5.1 签发Scheduler证书</h4>
```json
cd ~/TLS/k8s

cat > kube-scheduler-csr.json << EOF
{
  "CN": "system:kube-scheduler",
  "hosts": [],
  "key": {
    "algo": "rsa",
    "size": 2048
  },
  "names": [
    {
      "C": "CN",
      "L": "BeiJing",
      "ST": "BeiJing",
      "O": "system:masters",
      "OU": "System"
    }
  ]
}
EOF

# 生成证书
cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json -profile=kubernetes kube-scheduler-csr.json | cfssljson -bare kube-scheduler
````

<h4 id="ddEtk">3.5.2 生成Kubeconfig文件</h4>
```bash
KUBE_CONFIG="/opt/kubernetes/cfg/kube-scheduler.kubeconfig"
KUBE_APISERVER="https://192.168.124.21:6443"

kubectl config set-cluster kubernetes \
 --certificate-authority=/opt/kubernetes/ssl/ca.pem \
 --embed-certs=true \
 --server=${KUBE_APISERVER} \
  --kubeconfig=${KUBE_CONFIG}

kubectl config set-credentials kube-scheduler \
 --client-certificate=./kube-scheduler.pem \
 --client-key=./kube-scheduler-key.pem \
 --embed-certs=true \
 --kubeconfig=${KUBE_CONFIG}

kubectl config set-context default \
 --cluster=kubernetes \
 --user=kube-scheduler \
 --kubeconfig=${KUBE_CONFIG}

kubectl config use-context default --kubeconfig=${KUBE_CONFIG}

````

![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667393623329-96e20e19-5693-428f-8a33-74c846ba9633.png)

<h4 id="DppV0">3.5.3 Scheduler配置文件</h4>
```bash
cat > /opt/kubernetes/cfg/kube-scheduler.conf << EOF
KUBE_SCHEDULER_OPTS="--logtostderr=false \\
--v=2 \\
--log-dir=/opt/kubernetes/logs \\
--leader-elect \\
--kubeconfig=/opt/kubernetes/cfg/kube-scheduler.kubeconfig \\
--bind-address=127.0.0.1"
EOF
````

```bash
•--kubeconfig：连接apiserver配置文件
•--leader-elect：当该组件启动多个时，自动选举（HA）
```

<h4 id="ysb40">3.5.4 systemd管理Scheduler</h4>
```bash
cat > /etc/systemd/system/kube-scheduler.service << EOF
[Unit]
Description=Kubernetes Scheduler
Documentation=https://github.com/kubernetes/kubernetes

[Service]
EnvironmentFile=/opt/kubernetes/cfg/kube-scheduler.conf
ExecStart=/opt/kubernetes/bin/kube-scheduler \$KUBE_SCHEDULER_OPTS
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# 启动并设置开机启动

systemctl daemon-reload
systemctl restart kube-scheduler
systemctl enable kube-scheduler
systemctl status kube-scheduler

````

![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667393741067-df53f9c8-b2cc-41bd-9b79-de905e746b7e.png)

<h3 id="KQ5X9">3.6 Kubectl</h3>
<h4 id="RHyBd">3.6.1 签发kubectl连接集群证书</h4>
```json
cd ~/TLS/k8s

cat > admin-csr.json <<EOF
{
  "CN": "admin",
  "hosts": [],
  "key": {
    "algo": "rsa",
    "size": 2048
  },
  "names": [
    {
      "C": "CN",
      "L": "BeiJing",
      "ST": "BeiJing",
      "O": "system:masters",
      "OU": "System"
    }
  ]
}
EOF

# 生成证书
cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json -profile=kubernetes admin-csr.json | cfssljson -bare admin
````

<h4 id="H1kYS">3.6.2 生成Kubeconfig文件</h4>
```bash
mkdir /root/.kube

KUBE_CONFIG="/root/.kube/config"
KUBE_APISERVER="https://192.168.124.21:6443"

kubectl config set-cluster kubernetes \
 --certificate-authority=/opt/kubernetes/ssl/ca.pem \
 --embed-certs=true \
 --server=${KUBE_APISERVER} \
  --kubeconfig=${KUBE_CONFIG}

kubectl config set-credentials cluster-admin \
 --client-certificate=./admin.pem \
 --client-key=./admin-key.pem \
 --embed-certs=true \
 --kubeconfig=${KUBE_CONFIG}

kubectl config set-context default \
 --cluster=kubernetes \
 --user=cluster-admin \
 --kubeconfig=${KUBE_CONFIG}

kubectl config use-context default --kubeconfig=${KUBE_CONFIG}

````

![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667393994357-e3a2e27c-5191-448d-89a7-95dded82e66c.png)

<h4 id="ufDuw">3.6.3 通过kubectl查看集群组件状态</h4>
```bash
[root@master1 k8s]# kubectl get cs
Warning: v1 ComponentStatus is deprecated in v1.19+
NAME                 STATUS    MESSAGE                         ERROR
scheduler            Healthy   ok
controller-manager   Healthy   ok
etcd-0               Healthy   {"health":"true","reason":""}
````

如上说明所有 Master 节点组件正常

<h4 id="dhzIz">3.6.4  <font style="color:rgb(0,0,0);">授权kubelet-bootstrap用户允许请求证书</font></h4>
```bash
kubectl create clusterrolebinding kubelet-bootstrap \
--clusterrole=system:node-bootstrapper \
--user=kubelet-bootstrap
```

<h3 id="toD2H">3.7 Kubelet</h3>
如下操作还在Master节点操作，同时作为Worker Node节点

<h4 id="hpDxk">3.7.1 <font style="color:rgb(0,0,0);">配置参数文件</font></h4>
```yaml
cat > /opt/kubernetes/cfg/kubelet-config.yml << EOF
kind: KubeletConfiguration
apiVersion: kubelet.config.k8s.io/v1beta1
address: 0.0.0.0
port: 10250
readOnlyPort: 10255
cgroupDriver: cgroupfs
clusterDNS:
- 10.0.0.2
clusterDomain: cluster.local 
failSwapOn: false
authentication:
  anonymous:
    enabled: false
  webhook:
    cacheTTL: 2m0s
    enabled: true
  x509:
    clientCAFile: /opt/kubernetes/ssl/ca.pem 
authorization:
  mode: Webhook
  webhook:
    cacheAuthorizedTTL: 5m0s
    cacheUnauthorizedTTL: 30s
evictionHard:
  imagefs.available: 15%
  memory.available: 100Mi
  nodefs.available: 10%
  nodefs.inodesFree: 5%
maxOpenFiles: 1000000
maxPods: 110
EOF
```

<h4 id="HJaYw">3.7.2 生成kubelet初次加入集群引导kubeconfig文件</h4>
```bash
KUBE_CONFIG="/opt/kubernetes/cfg/bootstrap-kubelet.kubeconfig"
KUBE_APISERVER="https://192.168.124.21:6443" # apiserver IP:PORT
TOKEN="c47ffb939f5ca36231d9e3121a252940" # 与token.csv里保持一致

# 生成 kubelet bootstrap kubeconfig 配置文件

kubectl config set-cluster kubernetes \
 --certificate-authority=/opt/kubernetes/ssl/ca.pem \
 --embed-certs=true \
 --server=${KUBE_APISERVER} \
  --kubeconfig=${KUBE_CONFIG}

kubectl config set-credentials "kubelet-bootstrap" \
 --token=${TOKEN} \
  --kubeconfig=${KUBE_CONFIG}

kubectl config set-context default \
 --cluster=kubernetes \
 --user="kubelet-bootstrap" \
 --kubeconfig=${KUBE_CONFIG}

kubectl config use-context default --kubeconfig=${KUBE_CONFIG}

````

<h4 id="FZ85O">3.7.3 systemd管理Kubelet</h4>
```bash
cat > /etc/systemd/system/kubelet.service << EOF
[Unit]
Description=Kubernetes Kubelet
After=containerd.service
Requires=containerd.service

[Service]
ExecStart=/opt/kubernetes/bin/kubelet \
    --bootstrap-kubeconfig=/opt/kubernetes/cfg/bootstrap-kubelet.kubeconfig  \
    --kubeconfig=/opt/kubernetes/cfg/kubelet.kubeconfig \
    --config=/opt/kubernetes/cfg/kubelet-config.yml \
    --container-runtime=remote  \
    --runtime-request-timeout=15m  \
    --container-runtime-endpoint=unix:///run/containerd/containerd.sock  \
    --cgroup-driver=systemd \
    --node-labels=node.kubernetes.io/node=''
#   --feature-gates=IPv6DualStack=true
Restart=on-failure
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# 启动并设置开机启动
systemctl daemon-reload
systemctl restart kubelet
systemctl enable kubelet
systemctl status kubelet
````

```yaml
•--hostname-override：显示名称，集群中唯一
•--network-plugin：启用CNI
•--kubeconfig：空路径，会自动生成，后面用于连接apiserver
•--bootstrap-kubeconfig：首次启动向apiserver申请证书
•--config：配置参数文件
•--cert-dir：kubelet证书生成目录
•--pod-infra-container-image：管理Pod网络容器的镜像
```

<h4 id="kxNwH">3.7.4 <font style="color:rgb(0,0,0);">批准kubelet证书申请并加入集群</font></h4>
```bash
# 查看kubelet证书请求
[root@master1 k8s]# kubectl get csr
NAME                                                   AGE   SIGNERNAME                                    REQUESTOR           REQUESTEDDURATION   CONDITION
node-csr-guKp4GT08iDuBUXBnfteEGA0-2klqrY3sB46P5xYeJs   11s   kubernetes.io/kube-apiserver-client-kubelet   kubelet-bootstrap   <none>              Pending

# 批准申请

[root@master1 k8s]# kubectl certificate approve node-csr-guKp4GT08iDuBUXBnfteEGA0-2klqrY3sB46P5xYeJs
certificatesigningrequest.certificates.k8s.io/node-csr-guKp4GT08iDuBUXBnfteEGA0-2klqrY3sB46P5xYeJs approved

# 查看节点

[root@master1 k8s]# kubectl get node
NAME STATUS ROLES AGE VERSION
k8s-master NotReady <none> 3s v1.24.7

````

![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667717909532-d5f16e01-1089-4739-88f5-cae2b27f7d5c.png)

<font style="color:rgb(0,0,0);">注：由于网络插件还没有部署，节点会没有准备就绪 NotReady</font>

<h3 id="SpGwM"><font style="color:rgb(0,0,0);">3.8 Kube-Proxy</font></h3>
<h4 id="D0arL">3.8.1 Kube-Proxy配置文件</h4>
```bash
cat > /opt/kubernetes/cfg/kube-proxy.conf << EOF
KUBE_PROXY_OPTS="--logtostderr=false \\
--v=2 \\
--log-dir=/opt/kubernetes/logs \\
--config=/opt/kubernetes/cfg/kube-proxy-config.yml"
EOF
````

<h4 id="n1paS">3.8.2 配置文件参数</h4>
```yaml
cat > /opt/kubernetes/cfg/kube-proxy-config.yml << EOF
kind: KubeProxyConfiguration
apiVersion: kubeproxy.config.k8s.io/v1alpha1
bindAddress: 0.0.0.0
metricsBindAddress: 0.0.0.0:10249
clientConnection:
  kubeconfig: /opt/kubernetes/cfg/kube-proxy.kubeconfig
hostnameOverride: 192.168.124.21
clusterCIDR: 10.1.0.0/16
mode: ipvs
ipvs:
  scheduler: "rr"
iptables:
  masqueradeAll: true
EOF
```

<h4 id="yCObu">3.8.3 签发Kube-Proxy证书</h4>
```bash
cd ~/TLS/k8s

cat > kube-proxy-csr.json << EOF
{
"CN": "system:kube-proxy",
"hosts": [],
"key": {
"algo": "rsa",
"size": 2048
},
"names": [
{
"C": "CN",
"L": "BeiJing",
"ST": "BeiJing",
"O": "k8s",
"OU": "System"
}
]
}
EOF

# 生成证书

cfssl gencert -ca=ca.pem -ca-key=ca-key.pem -config=ca-config.json -profile=kubernetes kube-proxy-csr.json | cfssljson -bare kube-proxy

````

<h4 id="WVtom">3.8.4 <font style="color:rgb(0,0,0);">生成kube-proxy.kubeconfig文件</font></h4>
```bash
KUBE_CONFIG="/opt/kubernetes/cfg/kube-proxy.kubeconfig"
KUBE_APISERVER="https://192.168.124.21:6443"

kubectl config set-cluster kubernetes \
  --certificate-authority=/opt/kubernetes/ssl/ca.pem \
  --embed-certs=true \
  --server=${KUBE_APISERVER} \
  --kubeconfig=${KUBE_CONFIG}

kubectl config set-credentials kube-proxy \
  --client-certificate=./kube-proxy.pem \
  --client-key=./kube-proxy-key.pem \
  --embed-certs=true \
  --kubeconfig=${KUBE_CONFIG}

kubectl config set-context default \
  --cluster=kubernetes \
  --user=kube-proxy \
  --kubeconfig=${KUBE_CONFIG}

kubectl config use-context default --kubeconfig=${KUBE_CONFIG}
````

<h4 id="S551a">3.8.5 systemd管理Kube-Proxy</h4>
```bash
cat > /etc/systemd/system/kube-proxy.service << EOF
[Unit]
Description=Kubernetes Proxy
After=network.target

[Service]
EnvironmentFile=/opt/kubernetes/cfg/kube-proxy.conf
ExecStart=/opt/kubernetes/bin/kube-proxy \$KUBE_PROXY_OPTS
Restart=on-failure
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# 启动并设置开机启动

systemctl daemon-reload
systemctl restart kube-proxy
systemctl enable kube-proxy
systemctl status kube-proxy

````

<h4 id="HgtMc">3.8.6 添加node节点</h4>
```bash
# 将文件和证书复制到node节点
scp /opt/kubernetes/bin/kube{let,-proxy} root@k8s-node1:/opt/kubernetes/bin
scp /opt/kubernetes/bin/kube{let,-proxy} root@k8s-node2:/opt/kubernetes/bin

scp /opt/kubernetes/cfg/*kube{let*,-proxy*} root@k8s-node1:/opt/kubernetes/cfg/
scp /opt/kubernetes/cfg/*kube{let*,-proxy*} root@k8s-node2:/opt/kubernetes/cfg/

scp -r /opt/kubernetes/ssl/ root@k8s-node1:/opt/kubernetes
scp -r /opt/kubernetes/ssl/ root@k8s-node2:/opt/kubernetes

scp /etc/systemd/system/kube{let*,-proxy*} root@k8s-node1:/etc/systemd/system
scp /etc/systemd/system/kube{let*,-proxy*} root@k8s-node2:/etc/systemd/system

# node启动kubelet、kube-proxy
systemctl start kubelet kube-proxy
systemctl enable kubelet kube-proxy
systemctl status kubelet kube-proxy
````

<h4 id="kwdgZ">3.8.7 批准node节点的证书申请</h4>
```bash
kubectl certificate approve node-csr-zZh4jz9iFeJQp_brVPVA_oStyEZCrRA6I0rYbGJThY0
kubectl certificate approve  node-csr-eOUgX4kAnvZ96kTRPZQAdQY7x8m2UoSXAHc7aW7WhHg
```

![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667973886394-21b27a0a-10b7-40e8-aed9-d728ada64578.png)

![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667973904124-90b43ff0-3c41-4310-a94b-9c6c303ad4d8.png)

<h3 id="W0u7W">3.9 CNI网络插件Calico</h3>
<h4 id="wPL0b">3.9.1 下载calico</h4>
```bash
wget https://docs.projectcalico.org/manifests/calico.yaml --no-check-certificate

# 将 CALICO_IPV4POOL_CIDR 参数注释取消，并修改 ip 地址段为上面的 cluster-cidr 地址

- name: CALICO_IPV4POOL_CIDR
  value: "10.1.0.0/16"

````

![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667718904229-21043ba7-0167-455f-9079-c4bd2f9b832b.png)

<h4 id="cUzfQ">3.9.2 通过yaml文件部署calico</h4>
```bash
[root@master1 TLS]# kubectl apply -f calico.yaml
````

<h4 id="arrcc">![](https://cdn.nlark.com/yuque/0/2022/png/29476003/1667975355984-8461cc1c-a5e4-4c77-8475-ee18d40a78c4.png)</h4>
<h4 id="ftBLQ">3.9.3 授权apiserver访问kubelet</h4>
```yaml
cat > apiserver-to-kubelet-rbac.yaml << EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  annotations:
    rbac.authorization.kubernetes.io/autoupdate: "true"
  labels:
    kubernetes.io/bootstrapping: rbac-defaults
  name: system:kube-apiserver-to-kubelet
rules:
  - apiGroups:
      - ""
    resources:
      - nodes/proxy
      - nodes/stats
      - nodes/log
      - nodes/spec
      - nodes/metrics
      - pods/log
    verbs:
      - "*"
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: system:kube-apiserver
  namespace: ""
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:kube-apiserver-to-kubelet
subjects:
  - apiGroup: rbac.authorization.k8s.io
    kind: User
    name: kubernetes
EOF

kubectl apply -f apiserver-to-kubelet-rbac.yaml

```





```
