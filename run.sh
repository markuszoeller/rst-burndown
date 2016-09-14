#!/bin/bash

set -e

cd $(dirname $0)
if [ ! -d "nova" ]; then
  git clone "https://github.com/openstack/nova.git"
fi
pushd nova > /dev/null
git pull 2>&1 > /dev/null
popd > /dev/null
./api-ref-burndown.py
# Error message `git: 'ci' is not a git command.`. Maybe an alias?
# git ci -m "Updated csv" > /dev/null
