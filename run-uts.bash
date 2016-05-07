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
    local children=$(pgrep -P ${ppid})
    echo "Children are $children"
    for cpid in $children 
    do
        killchildren "${cpid}" "$signal"
        echo "killing $cpid" >&2
        kill -${signal} ${cpid}
    done
}

# Get the python version
pyver=$(python --version 2>&1 | sed -nE 's/Python ([0-9]+.[0-9]+.[0-9]+)/\1/p')
pymajver=${pyver%%.*}
pyminver=${pyver#*.}
pypatchver=${pyminver#*.}
pyminver=${pyminver%.*}

for signal in INT TERM ABRT QUIT
do
    trap \
"echo \"Kill children $signal\";"\
"killchildren $$ ${signal};"\
"trap \"echo Kill children KILL; killchildren $$ KILL\" ${signal}" $signal
done

find . -name "*.pyc" -delete

if (( ${#tests} > 0 ))
then
    python -m unittest unittest_logging "${tests[@]}" &
    child_pid=$!
else
    if (( pymajver > 2 ))
    then
        python -m unittest &
        child_pid=$!
    else
        python -m unittest discover &
        child_pid=$!
    fi
fi

echo "Waiting for child $child_pid"
wait "${child_pid}"
rc=$?
echo "child exited with $rc"
exit $rc
