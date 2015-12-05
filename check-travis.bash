#/bin/bash
#
# Runs all commands that travis would run from the .travis.yml and tells you
# whether travis should pass or not.
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

exec 3>/dev/null
#exec 3>&1

travis_file=.travis.yml

if [[ ! -e $travis_file ]]
then
    echo "Can't find travis file at $travis_file" >&2
    exit 127
fi

in_commands=0
commands_attempted=0
commands_succeeded=0
commands_failed=0
# read -r to make sure backslashes are included since we need to execute
# exactly what is there.
while read -r travis_line
do
    if [[ $travis_line =~ ^script:$ ]]
    then
        in_commands=1
        continue
    fi

    if (( ! in_commands ))
    then
        continue
    fi

    if [[ ! $travis_line =~ ^"- " ]]
    then
        # Exhausted commands.
        break
    fi
    travis_cmd="${travis_line#- }"
    (( commands_attempted++ ))
    echo "Run command: $travis_cmd"
    /bin/bash <<<"$travis_cmd" >&3 2>&1
    rc=$?
    if (( rc == 0 ))
    then
        echo "Success."
        (( commands_succeeded++ ))
    else
        echo "Failed!"
        (( commands_failed++ ))
    fi
done < "${travis_file}"
echo "Done. $commands_attempted checks attempted, $commands_failed failed."
(( commands_failed == 0 ))

