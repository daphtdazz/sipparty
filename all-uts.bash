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

exec {stdout}>&1
exec 1>&2

error_exit () {
    rv = $1
    shift
    echo "$@" >&2
    exit ${rv}
}

DIR_SIP=sip

if [[ ! -d ${DIR_SIP} ]]
then
    error_exit 1 "${DIR_SIP} directory not in the current directory."
fi

for ut in "${DIR_SIP}"/{*,test/*}.py
do
    echo $ut
    if ! python "${ut}" 2>/dev/null
        then
        error_exit 2 "  Failed!"
        break
    fi
done
