while :
do
    if find sipparty docs -newer /tmp/sipparty-docs-build-last | read
        then sphinx-build -b html docs build
        touch /tmp/sipparty-docs-build-last
    fi
    sleep 0.3
done
