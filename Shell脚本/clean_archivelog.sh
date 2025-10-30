#!/bin/bash
# 描述：清理oracle归档日志

LOGFILE=/home/oracle/scripts/logs/rman_$(date +%Y%m%d).log

echo "[$(date)] 开始归档日志备份与清理..." >> $LOGFILE

rman target / << EOF >> $LOGFILE 2>&1
BACKUP ARCHIVELOG ALL DELETE INPUT;

DELETE NOPROMPT OBSOLETE;

CROSSCHECK ARCHIVELOG ALL;
DELETE NOPROMPT EXPIRED ARCHIVELOG ALL;

EXIT;
EOF

echo "[$(date)] 归档日志备份与清理完成。" >> $LOGFILE