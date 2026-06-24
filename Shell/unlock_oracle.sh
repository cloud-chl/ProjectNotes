#!/bin/bash
# 用途：unlock 修改并解锁oracle数据库已过期的用户和用户密码
#       unlimit 设置密码永不过期
#       display 查看用户状态

unlock_user(){
    sqlplus / as sysdba << EOF
    ALTER USER $unlock_user IDENTIFIED BY $unlock_user_passwd;
    ALTER USER $unlock_user ACCOUNT UNLOCK;
EOF

    if [ $? -eq 0 ];then
        echo "$unlock_user has been unlock, and the password has been changed to $unlock_user_passwd"
    else
        echo "failure."
    fi
}

unlimit_user(){
    sqlplus / as sysdba << EOF
    ALTER PROFILE DEFAULT LIMIT PASSWORD_LIFE_TIME UNLIMITED;
EOF

    if [ $? -eq 0 ];then
        echo "success."
    else
        echo "failure."
    fi
}

display_user(){
    sqlplus / as sysdba << EOF
    SELECT u.username, u.profile, u.account_status, u.expiry_date,
       p.resource_name, p.limit
    FROM dba_users u
    JOIN dba_profiles p ON u.profile = p.profile
    WHERE u.username = "$unlock_user"
    AND p.resource_name LIKE 'PASSWORD%';
EOF

    if [ $? -eq 0 ];then
        echo "success."
    else
        echo "failure."
    fi
}

main(){
    unlock_user=$1
    
    if [ $1 == "unlock" ];then
        unlock_user_passwd=$2
    fi

    CurrentUser=`whoami`
    if [ $CurrentUser != "oracle" ];then
        echo "Please use Oracle user to execute this script."
        exit 1
    fi

    export ORACLE_SID=ORCL  # 修改为你的SID
    export ORACLE_HOME=/app/software/oracle/product/11.2.0/db_1  # 修改为你的Oracle Home路径
    export PATH=$ORACLE_HOME/bin:$PATH

    case $i in
        unlock)
            unlock_user;
            ;;
        unlimit)
            unlimit_user;
            ;;
        display)
            display_user;
            ;;
        *)
            echo "invalid parameter."
            ;;
    esac
}

main
