#!/usr/bin/env bash
# Register a new ECS task definition pointing at IMAGE and cut over via
# CodeDeploy. Does not build. Fails if the service is not CODE_DEPLOY.
set -euo pipefail

REGION=""
CLUSTER=""
SERVICE=""
TASK_FAMILY=""
IMAGE=""
APP=""
DG=""
CONTAINER=""
PORT="8080"
HEALTH_URL=""
SKIP_WAIT=0

usage() {
	cat <<EOF
Usage: $(basename "$0") \\
  --region us-west-2 --cluster NAME --service NAME --task-family NAME \\
  --image registry/repo:sha --codedeploy-app NAME --codedeploy-group NAME \\
  --container NAME --port 8080 --health-url https://host/ready
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--region)
		REGION="$2"
		shift 2
		;;
	--cluster)
		CLUSTER="$2"
		shift 2
		;;
	--service)
		SERVICE="$2"
		shift 2
		;;
	--task-family)
		TASK_FAMILY="$2"
		shift 2
		;;
	--image)
		IMAGE="$2"
		shift 2
		;;
	--codedeploy-app)
		APP="$2"
		shift 2
		;;
	--codedeploy-group)
		DG="$2"
		shift 2
		;;
	--container)
		CONTAINER="$2"
		shift 2
		;;
	--port)
		PORT="$2"
		shift 2
		;;
	--health-url)
		HEALTH_URL="$2"
		shift 2
		;;
	--skip-wait)
		SKIP_WAIT=1
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		echo "unknown arg: $1" >&2
		usage
		exit 2
		;;
	esac
done

for v in REGION CLUSTER SERVICE TASK_FAMILY IMAGE APP DG CONTAINER HEALTH_URL; do
	[[ -n "${!v}" ]] || {
		echo "missing --$(echo "$v" | tr '[:upper:]' '[:lower:]' | tr '_' '-')" >&2
		usage
		exit 2
	}
done

aws_cli() { aws --region "$REGION" "$@"; }

CTRL=$(aws_cli ecs describe-services --cluster "$CLUSTER" --services "$SERVICE" \
	--query 'services[0].deploymentController.type' --output text)
if [[ "$CTRL" != "CODE_DEPLOY" ]]; then
	echo "service controller is ${CTRL}, not CODE_DEPLOY — this script is the wrong path" >&2
	exit 1
fi

aws_cli ecs describe-task-definition --task-definition "$TASK_FAMILY" \
	--query 'taskDefinition' --output json |
	jq --arg IMG "$IMAGE" --argjson PORT "$PORT" \
		'.containerDefinitions[0].image = $IMG |
     .containerDefinitions[0].stopTimeout = 60 |
     del(.taskDefinitionArn, .revision, .status, .requiresAttributes,
         .compatibilities, .registeredAt, .registeredBy)' \
		>/tmp/local-prod-td.json

TD_ARN=$(aws_cli ecs register-task-definition \
	--cli-input-json file:///tmp/local-prod-td.json \
	--query 'taskDefinition.taskDefinitionArn' --output text)
echo "task_definition=${TD_ARN}"

if [[ "$SKIP_WAIT" -eq 0 ]]; then
	while true; do
		ACTIVE_ID=$(aws_cli deploy list-deployments \
			--application-name "$APP" --deployment-group-name "$DG" \
			--include-only-statuses Created Queued InProgress Baking Ready \
			--query 'deployments[0]' --output text)
		ACTIVE_ID=${ACTIVE_ID%%$'\n'*}
		if [[ "$ACTIVE_ID" == "None" || -z "$ACTIVE_ID" ]]; then
			break
		fi
		echo "waiting on active deployment ${ACTIVE_ID}"
		sleep 15
	done
fi

APPSPEC=$(jq -n --arg TD "$TD_ARN" --arg CN "$CONTAINER" --argjson PORT "$PORT" '{
  version: 0.0,
  Resources: [{
    TargetService: {
      Type: "AWS::ECS::Service",
      Properties: {
        TaskDefinition: $TD,
        LoadBalancerInfo: { ContainerName: $CN, ContainerPort: $PORT }
      }
    }
  }]
}')
APPSPEC_ESCAPED=$(printf '%s' "$APPSPEC" | jq -Rs '.')
DEPLOYMENT_ID=$(aws_cli deploy create-deployment \
	--application-name "$APP" \
	--deployment-group-name "$DG" \
	--revision "{\"revisionType\":\"AppSpecContent\",\"appSpecContent\":{\"content\":${APPSPEC_ESCAPED}}}" \
	--query 'deploymentId' --output text)
echo "deployment_id=${DEPLOYMENT_ID}"

while true; do
	STATUS=$(aws_cli deploy get-deployment --deployment-id "$DEPLOYMENT_ID" \
		--query 'deploymentInfo.status' --output text)
	echo "codedeploy_status=${STATUS}"
	case "$STATUS" in
	Succeeded) break ;;
	Failed | Stopped)
		aws_cli deploy get-deployment --deployment-id "$DEPLOYMENT_ID" \
			--query 'deploymentInfo.{error:errorInformation,rollback:rollbackInfo}' --output json
		exit 1
		;;
	*) sleep 15 ;;
	esac
done

sleep 10
curl -sf --max-time 30 "$HEALTH_URL" >/dev/null
echo "health_ok=${HEALTH_URL}"
echo "image=${IMAGE}"
