#!/bin/bash

stat_file1=./temp/cpu_stat1.txt
stat_file2=./temp/cpu_stat2.txt

if [ ! -f ${stat_filel} ];then
    head -n 1 /proc/stat > ${stat_file1}
    exit
fi


head -n 1 /proc/stat > ${stat_file2}

# 取上一分钟的cpu使用率
user1=`cat ${stat_file1} | awk '{print $2}'`
nice1=`cat ${stat_file1} | awk '{print $3}'`
system1=`cat ${stat_file1} | awk '{print $4}'`
idle1=`cat ${stat_file1} | awk '{print $5}'`
iowait1=`cat ${stat_file1} | awk '{print $6}'`
irq1=`cat ${stat_file1} | awk '{print $7}'`
softirq1=`cat ${stat_file1} | awk '{print $8}'`
steal1=`cat ${stat_file1} | awk '{print $9}'`
guest1=`cat ${stat_file1} | awk '{print $10}'`    
guest_nice1=`cat ${stat_file1} | awk '{print $11}'`

user2=`cat ${stat_file2} | awk '{print $2}'`
nice2=`cat ${stat_file2} | awk '{print $3}'`
system2=`cat ${stat_file2} | awk '{print $4}'`
idle2=`cat ${stat_file2} | awk '{print $5}'`
iowait2=`cat ${stat_file2} | awk '{print $6}'`
irq2=`cat ${stat_file2} | awk '{print $7}'`
softirq2=`cat ${stat_file2} | awk '{print $8}'`
steal2=`cat ${stat_file2} | awk '{print $9}'`
guest2=`cat ${stat_file2} | awk '{print $10}'`    
guest_nice2=`cat ${stat_file2} | awk '{print $11}'`

user=`expr ${user2} - ${user1}`
nice=`expr ${nice2} - ${nice1}`
system=`expr ${system2} - ${system1}`
idle=`expr ${idle2} - ${idle1}`
iowait=`expr ${iowait2} - ${iowait1}`
irq=`expr ${irq2} - ${irq1}`
softirq=`expr ${softirq2} - ${softirq1}`    
steal=`expr ${steal2} - ${steal1}`
guest=`expr ${guest2} - ${guest1}`
guest_nice=`expr ${guest_nice2} - ${guest_nice1}`

cpu_total=`expr ${user} + ${nice} + ${system} + ${idle} + ${iowait} + ${irq} + ${softirq} + ${steal} + ${guest} + ${guest_nice}`

# cpu使用率
cpu_perc=`awk -v idle="${idle}" -v cpu_total="${cpu_total}" 'BEGIN{printf "%.2f\n", (1 - idle / cpu_total)*100}'`
echo "{
    \"cpuused\": ${cpu_perc}
}"

cat ${stat_file2} > ${stat_file1}
rm -rf ${stat_file2}