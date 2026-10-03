apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-service
  namespace: coffee-store
  annotations:
    eks.amazonaws.com/role-arn: ORDER_SERVICE_ROLE_ARN_PLACEHOLDER
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: notification-service
  namespace: coffee-store
  annotations:
    eks.amazonaws.com/role-arn: NOTIFICATION_SERVICE_ROLE_ARN_PLACEHOLDER
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: product-service
  namespace: coffee-store
spec:
  replicas: 1
  selector:
    matchLabels:
      app: product-service
  template:
    metadata:
      labels:
        app: product-service
    spec:
      securityContext:
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: product-service
          image: PRODUCT_IMAGE_PLACEHOLDER
          imagePullPolicy: IfNotPresent
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          ports:
            - name: http
              containerPort: 8000
          readinessProbe:
            httpGet: {path: /health, port: http}
            periodSeconds: 10
          livenessProbe:
            httpGet: {path: /health, port: http}
            initialDelaySeconds: 5
            periodSeconds: 20
          resources:
            requests: {cpu: 50m, memory: 64Mi}
            limits: {cpu: 250m, memory: 128Mi}
---
apiVersion: v1
kind: Service
metadata:
  name: product-service
  namespace: coffee-store
spec:
  selector: {app: product-service}
  ports:
    - {name: http, port: 8000, targetPort: http}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
  namespace: coffee-store
spec:
  replicas: 1
  strategy: {type: Recreate}
  selector:
    matchLabels:
      app: inventory-service
  template:
    metadata:
      labels:
        app: inventory-service
    spec:
      securityContext:
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: inventory-service
          image: INVENTORY_IMAGE_PLACEHOLDER
          imagePullPolicy: IfNotPresent
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          ports:
            - {name: http, containerPort: 8000}
          env:
            - {name: DATABASE_PATH, value: /data/inventory.db}
          volumeMounts:
            - {name: data, mountPath: /data}
          readinessProbe:
            httpGet: {path: /health, port: http}
            periodSeconds: 10
          livenessProbe:
            httpGet: {path: /health, port: http}
            initialDelaySeconds: 5
            periodSeconds: 20
          resources:
            requests: {cpu: 50m, memory: 64Mi}
            limits: {cpu: 250m, memory: 128Mi}
      volumes:
        - name: data
          persistentVolumeClaim: {claimName: inventory-data}
---
apiVersion: v1
kind: Service
metadata:
  name: inventory-service
  namespace: coffee-store
spec:
  selector: {app: inventory-service}
  ports:
    - {name: http, port: 8000, targetPort: http}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: coffee-store
spec:
  replicas: 1
  strategy: {type: Recreate}
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      securityContext:
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      serviceAccountName: order-service
      containers:
        - name: order-service
          image: ORDER_IMAGE_PLACEHOLDER
          imagePullPolicy: IfNotPresent
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          ports:
            - {name: http, containerPort: 8000}
          env:
            - {name: DATABASE_PATH, value: /data/orders.db}
            - {name: CATALOG_URL, value: http://product-service:8000}
            - {name: INVENTORY_URL, value: http://inventory-service:8000}
            - {name: EVENT_BUS_NAME, value: EVENT_BUS_NAME_PLACEHOLDER}
          volumeMounts:
            - {name: data, mountPath: /data}
          readinessProbe:
            httpGet: {path: /health, port: http}
            periodSeconds: 10
          livenessProbe:
            httpGet: {path: /health, port: http}
            initialDelaySeconds: 5
            periodSeconds: 20
          resources:
            requests: {cpu: 50m, memory: 64Mi}
            limits: {cpu: 250m, memory: 128Mi}
      volumes:
        - name: data
          persistentVolumeClaim: {claimName: order-data}
---
apiVersion: v1
kind: Service
metadata:
  name: order-service
  namespace: coffee-store
spec:
  selector: {app: order-service}
  ports:
    - {name: http, port: 8000, targetPort: http}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: notification-service
  namespace: coffee-store
spec:
  replicas: 1
  strategy: {type: Recreate}
  selector:
    matchLabels:
      app: notification-service
  template:
    metadata:
      labels:
        app: notification-service
    spec:
      securityContext:
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      serviceAccountName: notification-service
      containers:
        - name: notification-service
          image: NOTIFICATION_IMAGE_PLACEHOLDER
          imagePullPolicy: IfNotPresent
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          ports:
            - {name: http, containerPort: 8000}
          env:
            - {name: DATABASE_PATH, value: /data/notifications.db}
            - {name: SQS_QUEUE_URL, value: ORDER_NOTIFICATION_QUEUE_URL_PLACEHOLDER}
            - {name: SNS_TOPIC_ARN, value: ORDER_NOTIFICATION_TOPIC_ARN_PLACEHOLDER}
          volumeMounts:
            - {name: data, mountPath: /data}
          readinessProbe:
            httpGet: {path: /health, port: http}
            periodSeconds: 10
          livenessProbe:
            httpGet: {path: /health, port: http}
            initialDelaySeconds: 5
            periodSeconds: 20
          resources:
            requests: {cpu: 50m, memory: 64Mi}
            limits: {cpu: 250m, memory: 128Mi}
      volumes:
        - name: data
          persistentVolumeClaim: {claimName: notification-data}
---
apiVersion: v1
kind: Service
metadata:
  name: notification-service
  namespace: coffee-store
spec:
  selector: {app: notification-service}
  ports:
    - {name: http, port: 8000, targetPort: http}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: coffee-store
spec:
  replicas: 1
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      securityContext:
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: frontend
          image: FRONTEND_IMAGE_PLACEHOLDER
          imagePullPolicy: IfNotPresent
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          ports:
            - {name: http, containerPort: 8080}
          volumeMounts:
            - {name: nginx-cache, mountPath: /var/cache/nginx}
            - {name: nginx-run, mountPath: /var/run}
          readinessProbe:
            httpGet: {path: /health, port: http}
            periodSeconds: 10
          livenessProbe:
            httpGet: {path: /health, port: http}
            initialDelaySeconds: 5
            periodSeconds: 20
          resources:
            requests: {cpu: 10m, memory: 16Mi}
            limits: {cpu: 100m, memory: 64Mi}
      volumes:
        - name: nginx-cache
          emptyDir: {}
        - name: nginx-run
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: coffee-store
spec:
  selector: {app: frontend}
  ports:
    - {name: http, port: 80, targetPort: http}
