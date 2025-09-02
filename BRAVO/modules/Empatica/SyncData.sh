#!/bin/bash 

LOCKFILE=${BRAVO_PATH}/BRAVO/modules/Empatica/CreateEmpaticaStructure.lock
if [ -e ${LOCKFILE} ] && kill -0 `cat ${LOCKFILE}`; then
    echo "already running"
    exit
fi

aws s3 sync s3://${EMPATICA_BUCKET}/ /data/Empatica

rm -f ${BRAVO_PATH}/BRAVO/modules/Empatica/CreateEmpaticaStructure.lock