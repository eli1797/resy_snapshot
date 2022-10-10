remove the __init__ == main

add 

```
def lambda_handler(event, context):
    main()

    return {
        "text": "execution of resy requests done"
    }

```

### To deploy:
Copy to zip in a file named lambda_function.py
Or just copy paste the code into the lambda editor and click deploy.