@Library('jenkins-lib') _

pipeline {
    agent any

    environment {
        IMAGE_NAME = "arpitdixit78/mybot:latest"
    }

    stages {

        stage('Clone Code') {
            steps {
                git 'https://github.com/ARPITDIXIT789/PATCH-BOT.git'
            }
        }

        stage('Docker Login') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'docker-creds',
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh "echo $DOCKER_PASS | docker login -u $DOCKER_USER --password-stdin"
                }
            }
        }

        stage('Build & Push Image') {
            steps {
                script {
                    dockerBuildPush(env.IMAGE_NAME)
                }
            }
        }

        stage('Deploy Container') {
            steps {
                script {
                    deployContainer(env.IMAGE_NAME)
                }
            }
        }
    }
}
