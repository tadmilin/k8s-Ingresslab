@echo off
rem Deploy the id-624 lab to the running minikube cluster. Run from the repository root.
rem Needs: minikube (started) and kubectl on PATH.
minikube addons enable ingress || exit /b 1
kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=180s || exit /b 1
kubectl apply -k . || exit /b 1
kubectl wait --namespace id624 --for=condition=available deployment --all --timeout=180s || exit /b 1
kubectl get all,ingress,pvc -n id624
for /f %%i in ('minikube ip') do echo.& echo Add this line to the hosts file: %%i  www.id-624.com  admin.id-624.com
