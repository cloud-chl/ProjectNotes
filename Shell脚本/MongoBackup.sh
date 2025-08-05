#!/bin/bash

# 设置变量
MONGO_DUMP_PATH="/mongodb/bin/mongodump" # mongodump 工具路径
BACKUP_DIR="/data/backup/mongodb"                               # 备份文件存储目录
DB_NAME="sys"                                                  # 需要备份的数据库名称
USERNAME="root"                                                 # 登录用户名
PASSWORD='admin@123'                                             # 登录密码
AUTH_DB="admin"                                                 # 认证数据库
REPLICA_SET_HOST="rs/192.168.205.205:27017"                     # 副本集地址
LOG_FILE="/data/backup/mongodb/mongodb_backup.log"

# 创建备份目录（如果不存在）
mkdir -p "$BACKUP_DIR"

# 创建日期格式化目录名和 tar 包名
DATE=$(date +"%Y%m%d")
CURRENT_BACKUP_DIR="$BACKUP_DIR/$DATE"
TAR_FILE="$BACKUP_DIR/${DATE}_${DB_NAME}.tar.gz"

# 删除一个月前的备份（保留最近30天内的 .tar.gz 文件）
find "$BACKUP_DIR" -maxdepth 1 -type f -name "*_${DB_NAME}.tar.gz" -mtime +30 | while read file; do
    echo "$(date +"%Y-%m-%d %H:%M:%S") Deleting old backup: $file" >>"$LOG_FILE"
    rm -f "$file"
done

# 清理旧的未打包的备份目录（可选）
find "$BACKUP_DIR" -maxdepth 1 -type d -name "[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]" -mtime +1 | while read dir; do
    echo "$(date +"%Y-%m-%d %H:%M:%S") Cleaning up incomplete backup: $dir" >>"$LOG_FILE"
    rm -rf "$dir"
done

# 执行备份
echo "$(date +"%Y-%m-%d %H:%M:%S") Starting backup..." >>"$LOG_FILE"

"$MONGO_DUMP_PATH" \
    --host "$REPLICA_SET_HOST" \
    --readPreference secondaryPreferred \
    --username "$USERNAME" --password "$PASSWORD" --authenticationDatabase "$AUTH_DB" \
    --db "$DB_NAME" --out "$CURRENT_BACKUP_DIR" >>"$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    echo "$(date +"%Y-%m-%d %H:%M:%S") Backup failed." >>"$LOG_FILE"
    exit 1
fi

# 打包为 .tar.gz
echo "$(date +"%Y-%m-%d %H:%M:%S") Packing backup into tar.gz..." >>"$LOG_FILE"
cd "$BACKUP_DIR" || {
    echo "Failed to enter backup directory"
    exit 1
}
tar -czf "$TAR_FILE" "$DATE" >>"$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    echo "$(date +"%Y-%m-%d %H:%M:%S") Tar compression failed." >>"$LOG_FILE"
    exit 1
fi

# 删除原始备份目录
rm -rf "$CURRENT_BACKUP_DIR"

# 完成
echo "$(date +"%Y-%m-%d %H:%M:%S") Backup and compression completed successfully." >>"$LOG_FILE"
