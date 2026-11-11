# Secrets of the zitadel tenant overlay

The overlay does not contain Secrets. Create these five in the overlay's namespace
(`zitadel` here) before the first sync, as SealedSecrets (or ESO). Names and keys are
the contract in `k8s/components/apps/auth/zitadel/contract.yaml`.

```bash
cp zitadel-masterkey.env.example zitadel-masterkey.env       # edit the values
# ... one .env per file above, then seal each one:
kubectl create secret generic zitadel-masterkey -n zitadel \
  --from-env-file=zitadel-masterkey.env --dry-run=client -o yaml \
  | kubeseal --format yaml > ../zitadel-masterkey-sealed.yaml

kubectl create secret generic zitadel-db-config -n zitadel \
  --from-file=config-yaml=zitadel-db-config.yaml --dry-run=client -o yaml \
  | kubeseal --format yaml > ../zitadel-db-config-sealed.yaml
```

Add the sealed files to `resources:`. Never commit the `.env` files.
`zitadel-bootstrap-env` is optional (users' initial passwords, IdP credentials).
