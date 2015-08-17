#!/bin/bash
# all-uts.sh
#
# Not a very elegant way of running all the UTs.
#
# Copyright 2015 David Park
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

typeset -a tests
PREPEND=sipparty.test
while (( $# > 0 ))
do
    if [[ $1 =~ (-l|--list) ]]
    then
        LIST=1
    else
        tests[${#tests}]=${PREPEND}.$1
    fi
    shift
done

if (( LIST ))
then
    for tpath in sipparty/test/test*.py
    do
        tfile=${tpath##*/}
        tname=${tfile%.py}
        echo "${tname}"
    done
    exit 0
fi

killchildren () {
    local ppid=$1
    local signal=$2
    local cpid

    if [[ -z ${signal} ]]
    then
        signal=KILL
    fi
    for cpid in $(pgrep -P ${ppid})
    do
        killchildren "${cpid}"
        echo "killing $cpid" >&2
        kill -${signal} ${cpid}
    done
}

for signal in INT TERM ABRT QUIT
do
    trap \
"echo \"Kill children $signal\";"\
"killchildren $$ ${signal};"\
"trap \"echo Kill children KILL; killchildren $$ KILL\" ${signal}" $signal
done

if (( ${#tests} > 0 ))
then
    python -m unittest unittest_logging "${tests[@]}" &
else
    python unittest_logging.py discover &
fi

while ! wait
do :
done

exit $?
